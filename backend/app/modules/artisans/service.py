"""Artisan use-cases (Req 23.1 to 23.8). Private contact details only ever leave through `staff_profile`;
the public serializer is a separate function that cannot reach them."""
from __future__ import annotations

import sqlite3
from typing import Any

from app import db
from app.errors import NotFound, ValidationFailed
from app.modules.production import api as production_api
from app.modules.products import api as products_api
from app.pagination import PageParams
from app.time_utils import utc_now_iso

from . import repository as repo
from .schemas import ArtisanIn

_CONTACT = {'phone': 'private_phone', 'email': 'private_email', 'address': 'private_address'}


# --- serializers ------------------------------------------------------------------------------------------------

def public_profile(row: sqlite3.Row) -> dict[str, Any]:
    """Visitor/customer view: identifier, public name, specialisation and story only (Req 23.5)."""
    return {'id': row['id'], 'publicName': row['name'], 'specialisation': row['specialisation'],
            'story': row['story']}


def staff_summary(row: sqlite3.Row) -> dict[str, Any]:
    return {'id': row['id'], 'name': row['name'], 'specialisation': row['specialisation'],
            'availability': row['availability'], 'story': row['story'], 'isActive': bool(row['is_active']),
            'privateContact': {'phone': row['private_phone'], 'email': row['private_email'],
                               'address': row['private_address']}}


def staff_profile(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    counts = production_api.counts_for_artisan(conn, row['id'])
    return {**staff_summary(row),
            'assignedProducts': products_api.products_for_artisan(conn, row['id']),
            'openJobCount': int(counts['open']), 'completedJobCount': int(counts['completed'])}


# --- staff use-cases --------------------------------------------------------------------------------------------

def _require(conn: sqlite3.Connection, artisan_id: int) -> sqlite3.Row:
    row = repo.get(conn, artisan_id)
    if row is None:
        raise NotFound('Artisan not found')
    return row


def _warnings(conn: sqlite3.Connection, artisan_id: int, availability: str) -> list[dict[str, Any]]:
    if availability != 'unavailable':
        return []
    job_ids = production_api.open_job_ids(conn, artisan_id)
    if not job_ids:
        return []
    return [{'code': 'open_jobs',
             'message': 'This artisan is unavailable but still has open production jobs',
             'jobIds': job_ids}]


def list_staff(conn: sqlite3.Connection, page: PageParams) -> tuple[list[dict[str, Any]], int]:
    rows, total = repo.list_all(conn, active_only=False, limit=page.limit, offset=page.offset)
    return [staff_summary(r) for r in rows], total


def get_staff(conn: sqlite3.Connection, artisan_id: int) -> dict[str, Any]:
    return staff_profile(conn, _require(conn, artisan_id))


def create(conn: sqlite3.Connection, body: ArtisanIn) -> dict[str, Any]:
    values: dict[str, Any] = {'name': body.name, 'specialisation': body.specialisation,
                              'availability': body.availability, 'story': body.story or '',
                              **{col: getattr(body, key) for key, col in _CONTACT.items()}}
    with db.transaction(conn):
        artisan_id = repo.insert(conn, values, utc_now_iso())
    return {**get_staff(conn, artisan_id), 'warnings': []}


def update(conn: sqlite3.Connection, artisan_id: int, body: ArtisanIn) -> dict[str, Any]:
    fields: dict[str, Any] = {'name': body.name, 'specialisation': body.specialisation,
                              'availability': body.availability}
    given = body.model_fields_set
    if body.story is not None:
        fields['story'] = body.story
    for key, col in _CONTACT.items():
        if key in given:  # explicit null clears, omission keeps
            fields[col] = getattr(body, key)
    with db.transaction(conn):
        _require(conn, artisan_id)
        repo.update(conn, artisan_id, fields, utc_now_iso())
        warnings = _warnings(conn, artisan_id, body.availability)
    return {**get_staff(conn, artisan_id), 'warnings': warnings}


def link_product(conn: sqlite3.Connection, product_id: str, artisan_id: int | None) -> dict[str, Any]:
    """Link or unlink; returns the updated assigned products of the affected artisan (Req 23.7)."""
    with db.transaction(conn):
        if artisan_id is not None and repo.get(conn, artisan_id) is None:
            raise ValidationFailed([{'field': 'artisanId', 'reason': 'unknown artisan'}])
        previous = products_api.set_product_artisan(conn, product_id, artisan_id)
    affected = artisan_id if artisan_id is not None else previous
    assigned = products_api.products_for_artisan(conn, affected) if affected is not None else []
    return {'productId': product_id, 'artisanId': artisan_id, 'assignedProducts': assigned}


# --- public use-cases -------------------------------------------------------------------------------------------

def list_public(conn: sqlite3.Connection, page: PageParams) -> tuple[list[dict[str, Any]], int]:
    rows, total = repo.list_all(conn, active_only=True, limit=page.limit, offset=page.offset)
    return [public_profile(r) for r in rows], total


def get_public(conn: sqlite3.Connection, artisan_id: int) -> dict[str, Any]:
    row = repo.get_active(conn, artisan_id)
    if row is None:
        raise NotFound('Artisan not found')
    return public_profile(row)
