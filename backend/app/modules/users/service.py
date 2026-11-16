"""Business rules for users, profiles and addresses.

Write operations that stand alone open their own BEGIN IMMEDIATE transaction. `create_user` does not:
it runs inside the caller's transaction (auth registration, seed script) so that creation stays atomic there.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Callable, Optional

from ... import db
from ...errors import Conflict, NotFound
from ...time_utils import utc_now_iso
from ..products import api as products_api
from . import repository as repo
from .schemas import AddressInput, ProfileUpdate

ROLES = ('customer', 'seller', 'admin', 'artisan')


def _user_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {'id': row['id'], 'name': row['name'], 'email': row['email'], 'phone': row['phone'], 'role': row['role']}


def _address_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {'id': row['id'], 'recipientName': row['recipient_name'], 'phone': row['phone'], 'line1': row['line1'],
            'line2': row['line2'], 'postcode': row['postcode'], 'city': row['city'], 'state': row['state'],
            'isDefault': bool(row['is_default'])}


def _address_fields(data: AddressInput) -> dict[str, Any]:
    f = data.model_dump()
    f['line2'] = f['line2'] or None
    return f


# ---- users -------------------------------------------------------------------------------------

def create_user(conn: sqlite3.Connection, *, name: str, email: str, password_hash: str, role: str = 'customer',
                phone: Optional[str] = None, is_demo: bool = False) -> dict[str, Any]:
    """Insert a user inside the caller's transaction. Duplicate e-mail (case-insensitive) raises 409."""
    if role not in ROLES:
        raise ValueError(f'unknown role: {role}')
    email = email.strip()
    try:
        user_id = repo.insert_user(conn, name=name, email=email, email_lower=email.lower(), password_hash=password_hash,
                                   phone=phone, role=role, is_demo=is_demo, now=utc_now_iso())
    except sqlite3.IntegrityError as exc:
        if 'email_lower' in str(exc):
            raise Conflict('An account with this email already exists', code='email_taken') from None
        raise
    return get_user(conn, user_id)


def get_user(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    row = repo.get_user(conn, user_id)
    if row is None:
        raise NotFound('User not found')
    return _user_dict(row)


def find_by_email(conn: sqlite3.Connection, email: str) -> Optional[dict[str, Any]]:
    row = repo.get_user_by_email_lower(conn, email.strip().lower())
    if row is None:
        return None
    return {**_user_dict(row), 'isActive': bool(row['is_active'])}


def get_account(conn: sqlite3.Connection, user_id: int) -> Optional[dict[str, Any]]:
    """User by id including `isActive`; None when missing. Used by the session check."""
    row = repo.get_user(conn, user_id)
    if row is None:
        return None
    return {**_user_dict(row), 'isActive': bool(row['is_active'])}


def get_auth_record(conn: sqlite3.Connection, email: str) -> Optional[dict[str, Any]]:
    """Login lookup by email_lower. The only function that returns password_hash; auth must not echo it."""
    row = repo.get_auth_record(conn, email.strip().lower())
    if row is None:
        return None
    return {**_user_dict(row), 'isActive': bool(row['is_active']), 'passwordHash': row['password_hash']}


def update_profile(conn: sqlite3.Connection, user_id: int, data: ProfileUpdate) -> dict[str, Any]:
    with db.transaction(conn):
        if repo.get_user(conn, user_id) is None:
            raise NotFound('User not found')
        repo.update_profile(conn, user_id, data.name, data.phone, utc_now_iso())
        return get_user(conn, user_id)


def change_role(conn: sqlite3.Connection, user_id: int, role: str) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError(f'unknown role: {role}')
    with db.transaction(conn):
        if repo.update_role(conn, user_id, role, utc_now_iso()) == 0:
            raise NotFound('User not found')
        return get_user(conn, user_id)


def deactivate_user(conn: sqlite3.Connection, user_id: int,
                    within: Optional[Callable[[sqlite3.Connection], Any]] = None) -> dict[str, Any]:
    """Mark the account inactive. Revoking sessions is the auth module's job (it owns `sessions`):
    the composition layer passes it as `within`, which runs in the same transaction."""
    with db.transaction(conn):
        if repo.deactivate(conn, user_id, utc_now_iso()) == 0:
            raise NotFound('User not found')
        if within is not None:
            within(conn)
        return get_user(conn, user_id)


def favourite_product_ids(conn: sqlite3.Connection, user_id: int) -> list[str]:
    """All favourite ids including those of inactive products (associations are retained, Req 10.9)."""
    return repo.favourite_product_ids(conn, user_id)


# ---- favourites --------------------------------------------------------------------------------

def list_favourites(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    """Active favourite products, newest first. Inactive products are omitted but their rows stay (Req 10.9)."""
    return products_api.get_active_products(conn, repo.favourite_product_ids(conn, user_id))


def add_favourite(conn: sqlite3.Connection, user_id: int, product_id: str) -> None:
    """Idempotent add. Missing or inactive products are rejected with 409 `product_unavailable` (Req 10.5)."""
    with db.transaction(conn):
        if product_id not in products_api.active_product_ids(conn, [product_id]):
            raise Conflict('This product is not available', code='product_unavailable')
        repo.add_favourite(conn, user_id, product_id, utc_now_iso())


def remove_favourite(conn: sqlite3.Connection, user_id: int, product_id: str) -> None:
    """Idempotent remove (Req 10.4)."""
    with db.transaction(conn):
        repo.remove_favourite(conn, user_id, product_id)


def merge_favourites(conn: sqlite3.Connection, user_id: int, product_ids: list[str]) -> list[dict[str, Any]]:
    """Merge locally saved ids without duplicates. Unavailable ids are skipped, not an error (Req 10.10)."""
    with db.transaction(conn):
        valid = products_api.active_product_ids(conn, product_ids)
        now = utc_now_iso()
        for pid in dict.fromkeys(product_ids):
            if pid in valid:
                repo.add_favourite(conn, user_id, pid, now)
    return list_favourites(conn, user_id)


# ---- addresses ---------------------------------------------------------------------------------

def list_addresses(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    return [_address_dict(r) for r in repo.list_addresses(conn, user_id)]


def _require_address(conn: sqlite3.Connection, user_id: int, address_id: int) -> sqlite3.Row:
    row = repo.get_address(conn, user_id, address_id)
    if row is None:
        raise NotFound('Address not found')  # identical for missing and foreign ids (Req 7.8)
    return row


def create_address(conn: sqlite3.Connection, user_id: int, data: AddressInput) -> dict[str, Any]:
    now = utc_now_iso()
    with db.transaction(conn):
        if data.is_default:
            repo.clear_default(conn, user_id)
        address_id = repo.insert_address(conn, user_id, _address_fields(data), data.is_default, now)
        return _address_dict(_require_address(conn, user_id, address_id))


def update_address(conn: sqlite3.Connection, user_id: int, address_id: int, data: AddressInput) -> dict[str, Any]:
    """Update fields. `is_default=True` makes this the single default; False leaves the default flag unchanged."""
    now = utc_now_iso()
    with db.transaction(conn):
        _require_address(conn, user_id, address_id)
        repo.update_address(conn, user_id, address_id, _address_fields(data), now)
        if data.is_default:
            repo.clear_default(conn, user_id)
            repo.set_default(conn, user_id, address_id, now)
        return _address_dict(_require_address(conn, user_id, address_id))


def set_default_address(conn: sqlite3.Connection, user_id: int, address_id: int) -> dict[str, Any]:
    now = utc_now_iso()
    with db.transaction(conn):
        _require_address(conn, user_id, address_id)
        repo.clear_default(conn, user_id)
        repo.set_default(conn, user_id, address_id, now)
        return _address_dict(_require_address(conn, user_id, address_id))


def delete_address(conn: sqlite3.Connection, user_id: int, address_id: int) -> None:
    """Orders hold their own delivery copy, so deleting an address never touches them (Req 7.7)."""
    with db.transaction(conn):
        if repo.delete_address(conn, user_id, address_id) == 0:
            raise NotFound('Address not found')


def list_staff_user_ids(conn: sqlite3.Connection) -> list[int]:
    """Ids of active Staff_Users (seller and admin)."""
    return repo.list_staff_user_ids(conn)
