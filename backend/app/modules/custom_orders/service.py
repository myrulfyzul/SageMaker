"""Custom-order use-cases (Req 16, 25). Writes run in one BEGIN IMMEDIATE transaction; reference images are
all-or-nothing: validated first, written only when the whole request is valid, removed again if the DB write fails."""
from __future__ import annotations

import logging
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, BinaryIO, Optional

from app import db, uploads
from app.errors import Conflict, NotFound, ValidationFailed
from app.modules.artisans import api as artisans_api
from app.modules.notifications import api as notifications_api
from app.modules.production import api as production_api
from app.time_utils import today_local, utc_now_iso

from . import repository as repo

logger = logging.getLogger('sagemaker.custom_orders')

STATUSES = ('submitted', 'accepted', 'rejected', 'in_progress', 'completed')
TRANSITIONS: dict[str, tuple[str, ...]] = {
    'submitted': ('accepted', 'rejected'),
    'accepted': ('in_progress',),
    'rejected': (),
    'in_progress': ('completed',),
    'completed': (),
}
MAX_IMAGES = 5
MEDIA_URL_PREFIX = '/api/media/'
_CONTENT_TYPES = {'.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
_WHOLE_NUMBER = re.compile(r'^[0-9]+$')
_DATE = re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$')


# --- serializers ------------------------------------------------------------------------------------------------

def _dtos(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    images = repo.images_for(conn, [r['id'] for r in rows])
    jobs = production_api.job_summaries(conn, [r['production_job_id'] for r in rows if r['production_job_id']])
    result = []
    for r in rows:
        job = jobs.get(r['production_job_id']) if r['production_job_id'] else None
        result.append({
            'id': r['id'], 'userId': r['user_id'], 'productType': r['product_type'],
            'description': r['description'], 'quantity': r['quantity'], 'preferredDate': r['preferred_date'],
            'status': r['status'], 'estimatedPriceSen': r['estimated_price_sen'],
            'rejectReason': r['reject_reason'], 'artisanId': r['artisan_id'],
            'productionJobId': r['production_job_id'],
            'productionLabel': job['status'] if job else None,
            'productionProgressPercent': job['progressPercent'] if job else None,
            'imageUrls': [MEDIA_URL_PREFIX + name for name in images[r['id']]],
            'isDemo': bool(r['is_demo']), 'createdAt': r['created_at'], 'updatedAt': r['updated_at']})
    return result


def _page(items: list[dict[str, Any]], total: int, limit: int, offset: int) -> dict[str, Any]:
    return {'items': items, 'total': total, 'limit': limit, 'offset': offset}


def _require(conn: sqlite3.Connection, custom_order_id: int) -> sqlite3.Row:
    row = repo.get(conn, custom_order_id)
    if row is None:
        raise NotFound('Custom order not found')
    return row


# --- customer ---------------------------------------------------------------------------------------------------

def _validate_fields(product_type: Optional[str], description: Optional[str], quantity: Optional[str],
                     preferred_date: Optional[str], tz: str) -> tuple[str, str, int, str]:
    errors: list[dict[str, str]] = []

    def missing(field: str) -> None:
        errors.append({'field': field, 'reason': 'field is required'})

    ptype = (product_type or '').strip()
    desc = (description or '').strip()
    if product_type is None:
        missing('productType')
    elif not 1 <= len(ptype) <= 100:
        errors.append({'field': 'productType', 'reason': 'must be 1 to 100 characters'})
    if description is None:
        missing('description')
    elif not 10 <= len(desc) <= 2000:
        errors.append({'field': 'description', 'reason': 'must be 10 to 2000 characters'})
    qty = 0
    if quantity is None:
        missing('quantity')
    elif not _WHOLE_NUMBER.match(quantity.strip()) or not 1 <= int(quantity.strip()) <= 500:
        errors.append({'field': 'quantity', 'reason': 'must be a whole number from 1 to 500'})
    else:
        qty = int(quantity.strip())
    pdate = (preferred_date or '').strip()
    if preferred_date is None:
        missing('preferredDate')
    else:
        try:
            if not _DATE.match(pdate):
                raise ValueError
            parsed = date.fromisoformat(pdate)
        except ValueError:
            errors.append({'field': 'preferredDate', 'reason': 'must be a date in YYYY-MM-DD format'})
        else:
            if parsed < today_local(tz):
                errors.append({'field': 'preferredDate', 'reason': 'must be today or later'})
    if errors:
        raise ValidationFailed(errors)
    return ptype, desc, qty, pdate


def _validate_images(files: list[tuple[str, BinaryIO]]) -> list[tuple[bytes, str]]:
    """Read and validate every image; returns `(data, extension)` pairs. Nothing is stored here."""
    errors: list[dict[str, str]] = []
    if len(files) > MAX_IMAGES:
        errors.append({'field': 'images', 'reason': f'at most {MAX_IMAGES} images are allowed'})
    checked: list[tuple[bytes, str]] = []
    for index, (filename, stream) in enumerate(files[:MAX_IMAGES]):
        data = uploads.read_limited(stream)
        try:
            checked.append((data, uploads.validate_image(filename, data)))
        except ValidationFailed as exc:
            errors.extend({'field': f'images[{index}]', 'reason': d['reason']} for d in (exc.details or []))
    if errors:
        raise ValidationFailed(errors)
    return checked


def create(conn: sqlite3.Connection, user_id: int, *, product_type: Optional[str], description: Optional[str],
           quantity: Optional[str], preferred_date: Optional[str], files: list[tuple[str, BinaryIO]],
           media_dir: Path, tz: str) -> dict[str, Any]:
    ptype, desc, qty, pdate = _validate_fields(product_type, description, quantity, preferred_date, tz)
    images = _validate_images(files)
    stored: list[tuple[str, str, int]] = []
    try:
        for data, ext in images:
            stored.append((uploads.store_image(media_dir, data, ext), _CONTENT_TYPES[ext], len(data)))
        with db.transaction(conn):
            now = utc_now_iso()
            new_id = repo.insert(conn, user_id, ptype, desc, qty, pdate, 0, now)
            for name, content_type, size in stored:
                repo.insert_image(conn, new_id, name, content_type, size)
            notifications_api.custom_order_created(conn, str(new_id), user_id)
    except BaseException:
        for name, _, _ in stored:
            try:
                (Path(media_dir) / name).unlink(missing_ok=True)
            except OSError:
                logger.warning('Could not remove a custom-order image after a failed request')
        raise
    return _dtos(conn, [_require(conn, new_id)])[0]


def list_own(conn: sqlite3.Connection, user_id: int, limit: int, offset: int) -> dict[str, Any]:
    rows, total = repo.list_filtered(conn, user_id=user_id, status=None, limit=limit, offset=offset)
    return _page(_dtos(conn, rows), total, limit, offset)


def get_own(conn: sqlite3.Connection, user_id: int, custom_order_id: int) -> dict[str, Any]:
    row = repo.get_owned(conn, custom_order_id, user_id)
    if row is None:
        raise NotFound('Custom order not found')
    return _dtos(conn, [row])[0]


def media_file(conn: sqlite3.Connection, filename: str, user_id: int, role: str, media_dir: Path) -> tuple[Path, str]:
    """Path and content type of a reference image for its owner or any staff user; others get 404."""
    row = repo.image_by_filename(conn, filename)
    if row is None:
        raise NotFound()
    if role not in ('seller', 'admin') and not (role == 'customer' and row['owner_id'] == user_id):
        raise NotFound()
    path = Path(media_dir) / row['filename']
    if not path.is_file():
        raise NotFound()
    return path, row['content_type']


# --- staff ------------------------------------------------------------------------------------------------------

def list_staff(conn: sqlite3.Connection, status: Optional[str], limit: int, offset: int) -> dict[str, Any]:
    if status is not None and status not in STATUSES:
        raise ValidationFailed([{'field': 'status', 'reason': f'must be one of {", ".join(STATUSES)}'}])
    rows, total = repo.list_filtered(conn, user_id=None, status=status, limit=limit, offset=offset)
    return _page(_dtos(conn, rows), total, limit, offset)


def get_staff(conn: sqlite3.Connection, custom_order_id: int) -> dict[str, Any]:
    return _dtos(conn, [_require(conn, custom_order_id)])[0]


def _not_allowed(current: str, requested: str) -> Conflict:
    return Conflict(f'Cannot change custom order status from {current} to {requested}', code='invalid_transition',
                    details=[{'current': current, 'requested': requested}])


def _require_transition(row: sqlite3.Row, requested: str) -> None:
    if requested not in TRANSITIONS[row['status']]:
        raise _not_allowed(row['status'], requested)


def accept(conn: sqlite3.Connection, custom_order_id: int, price_sen: int) -> dict[str, Any]:
    with db.transaction(conn):
        row = _require(conn, custom_order_id)
        _require_transition(row, 'accepted')
        repo.set_accepted(conn, custom_order_id, price_sen, utc_now_iso())
        notifications_api.custom_order_status_changed(conn, str(custom_order_id), row['user_id'], row['status'],
                                                      'accepted')
    return get_staff(conn, custom_order_id)


def reject(conn: sqlite3.Connection, custom_order_id: int, reason: str) -> dict[str, Any]:
    with db.transaction(conn):
        row = _require(conn, custom_order_id)
        _require_transition(row, 'rejected')
        repo.set_rejected(conn, custom_order_id, reason, utc_now_iso())
        notifications_api.custom_order_status_changed(conn, str(custom_order_id), row['user_id'], row['status'],
                                                      'rejected')
    return get_staff(conn, custom_order_id)


def change_status(conn: sqlite3.Connection, custom_order_id: int, requested: str) -> dict[str, Any]:
    """Allowed transitions only (Req 25.10). `accepted` and `rejected` need a price or a reason, so they have their
    own endpoints; asking for them here is a validation error when the transition itself would be legal."""
    if requested not in STATUSES:
        raise ValidationFailed([{'field': 'status', 'reason': f'must be one of {", ".join(STATUSES)}'}])
    with db.transaction(conn):
        row = _require(conn, custom_order_id)
        _require_transition(row, requested)
        if requested in ('accepted', 'rejected'):
            endpoint = 'accept' if requested == 'accepted' else 'reject'
            raise ValidationFailed([{'field': 'status', 'reason': f'use the {endpoint} endpoint for this transition'}])
        repo.set_status(conn, custom_order_id, requested, utc_now_iso())
        notifications_api.custom_order_status_changed(conn, str(custom_order_id), row['user_id'], row['status'],
                                                      requested)
    return get_staff(conn, custom_order_id)


def assign_artisan(conn: sqlite3.Connection, custom_order_id: int, artisan_id: int) -> dict[str, Any]:
    """Store the assignment and create exactly one linked Production_Job, both or neither (Req 25.7, 25.8)."""
    with db.transaction(conn):
        row = _require(conn, custom_order_id)
        if row['status'] != 'accepted':
            raise Conflict('Only an accepted custom order can be assigned an artisan', code='invalid_transition',
                           details=[{'current': row['status'], 'requested': 'assigned'}])
        if row['artisan_id'] is not None or row['production_job_id'] is not None:
            raise Conflict('This custom order already has an artisan assigned', code='already_assigned')
        if not artisans_api.is_active(conn, artisan_id):
            raise ValidationFailed([{'field': 'artisanId', 'reason': 'artisan does not exist or is not active'}])
        job_id = production_api.create_job_for_custom_order(conn, custom_order_id, artisan_id, row['quantity'],
                                                            row['preferred_date'])
        repo.set_assignment(conn, custom_order_id, artisan_id, job_id, utc_now_iso())
    return get_staff(conn, custom_order_id)
