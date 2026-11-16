"""The only surface other modules may import from `users`. All functions take the caller's open connection."""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from . import service


def create_customer(conn: sqlite3.Connection, *, name: str, email: str, password_hash: str,
                    phone: Optional[str] = None, is_demo: bool = False) -> dict[str, Any]:
    """Create a `customer` user inside the caller's transaction. Raises Conflict(409) for a duplicate e-mail."""
    return service.create_user(conn, name=name, email=email, password_hash=password_hash, role='customer',
                               phone=phone, is_demo=is_demo)


def create_user(conn: sqlite3.Connection, *, name: str, email: str, password_hash: str, role: str,
                phone: Optional[str] = None, is_demo: bool = False) -> dict[str, Any]:
    """Create a user of any role. For the seed script only; public registration must use create_customer."""
    return service.create_user(conn, name=name, email=email, password_hash=password_hash, role=role,
                               phone=phone, is_demo=is_demo)


def get_user(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    return service.get_user(conn, user_id)


def find_by_email(conn: sqlite3.Connection, email: str) -> Optional[dict[str, Any]]:
    """Case-insensitive lookup through `email_lower`. Never includes the password hash."""
    return service.find_by_email(conn, email)


def get_account(conn: sqlite3.Connection, user_id: int) -> Optional[dict[str, Any]]:
    """User by id including `isActive`, or None. Never includes the password hash."""
    return service.get_account(conn, user_id)


def get_auth_record(conn: sqlite3.Connection, email: str) -> Optional[dict[str, Any]]:
    """Like find_by_email but includes `passwordHash` for credential verification."""
    return service.get_auth_record(conn, email)


def favourite_product_ids(conn: sqlite3.Connection, user_id: int) -> list[str]:
    return service.favourite_product_ids(conn, user_id)


def list_staff_user_ids(conn: sqlite3.Connection) -> list[int]:
    """Ids of active Staff_Users (seller and admin), for notification fan-out."""
    return service.list_staff_user_ids(conn)
