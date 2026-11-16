"""Production use-cases (Req 24). Production_Status lives only in `production_jobs`; nothing here writes the
Fulfilment_Status of an order (Req 24.10). Functions run in the caller's transaction unless noted."""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any, Optional

from app import db
from app.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.modules.artisans import api as artisans_api
from app.modules.inventory import api as inventory_api
from app.modules.notifications import api as notifications_api
from app.modules.orders import api as orders_api
from app.modules.products import api as products_api
from app.time_utils import today_local, utc_now_iso

from . import repository as repo
from .schemas import JobAssign, JobCreate, ProgressIn

STATUSES = ('order_confirmed', 'production_assigned', 'in_production', 'quality_checking', 'completed',
            'ready_for_fulfilment')
PRIORITIES = ('low', 'normal', 'high', 'urgent')
TRANSITIONS: dict[str, tuple[str, ...]] = {
    'order_confirmed': ('production_assigned',),
    'production_assigned': ('in_production',),
    'in_production': ('quality_checking',),
    'quality_checking': ('completed', 'in_production'),
    'completed': ('ready_for_fulfilment',),
    'ready_for_fulfilment': (),
}


# --- serializers ------------------------------------------------------------------------------------------------

def is_overdue(row: sqlite3.Row, today: date) -> bool:
    """Today is later than the deadline and the job is neither completed nor ready for fulfilment (Req 24.9)."""
    return bool(row['deadline']) and today.isoformat() > row['deadline'] and row['status'] not in repo.DONE_STATUSES


def job_dto(row: sqlite3.Row, today: date, *, product_name: Optional[str] = None,
            artisan_name: Optional[str] = None) -> dict[str, Any]:
    return {'id': row['id'], 'orderId': row['order_id'], 'orderLineId': row['order_line_id'],
            'customOrderId': row['custom_order_id'], 'productId': row['product_id'], 'productName': product_name,
            'artisanId': row['artisan_id'], 'artisanName': artisan_name, 'quantity': row['quantity'],
            'deadline': row['deadline'], 'priority': row['priority'], 'status': row['status'],
            'progressPercent': row['progress_percent'], 'notes': row['notes'], 'overdue': is_overdue(row, today),
            'isDemo': bool(row['is_demo']), 'createdAt': row['created_at'], 'updatedAt': row['updated_at']}


def _dtos(conn: sqlite3.Connection, rows: list[sqlite3.Row], today: date) -> list[dict[str, Any]]:
    product_names = products_api.product_names(conn, [r['product_id'] for r in rows if r['product_id']])
    artisan_names = artisans_api.names(conn, [r['artisan_id'] for r in rows if r['artisan_id'] is not None])
    return [job_dto(r, today, product_name=product_names.get(r['product_id']),
                    artisan_name=artisan_names.get(r['artisan_id'])) for r in rows]


def _require(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row:
    row = repo.get(conn, job_id)
    if row is None:
        raise NotFound('Production job not found')
    return row


# --- access control ---------------------------------------------------------------------------------------------

def assert_job_assigned_to_user(conn: sqlite3.Connection, job_id: int, user_id: int) -> None:
    """Artisan_User scoping (Req 6.7, 6.8): Forbidden unless the job is assigned to the user's Artisan profile.
    A missing job is also Forbidden, so an Artisan_User cannot probe which job ids exist."""
    row = repo.get(conn, job_id)
    artisan_id = artisans_api.artisan_id_for_user(conn, user_id)
    if row is None or artisan_id is None or row['artisan_id'] != artisan_id:
        raise Forbidden()


# --- queries ----------------------------------------------------------------------------------------------------

def list_jobs(conn: sqlite3.Connection, *, tz: str, status: Optional[str], artisan_id: Optional[int],
              priority: Optional[str], view: str, limit: int, offset: int,
              artisan_user_id: Optional[int] = None) -> dict[str, Any]:
    """Filters are AND-combined. An Artisan_User only ever sees jobs assigned to their own profile."""
    errors = []
    if status is not None and status not in STATUSES:
        errors.append({'field': 'status', 'reason': f'must be one of {", ".join(STATUSES)}'})
    if priority is not None and priority not in PRIORITIES:
        errors.append({'field': 'priority', 'reason': f'must be one of {", ".join(PRIORITIES)}'})
    if view not in ('list', 'board'):
        errors.append({'field': 'view', 'reason': 'must be list or board'})
    if errors:
        raise ValidationFailed(errors)
    today = today_local(tz)
    empty = False
    if artisan_user_id is not None:
        own = artisans_api.artisan_id_for_user(conn, artisan_user_id)
        if own is None or (artisan_id is not None and artisan_id != own):
            empty = True
        artisan_id = own
    if empty:
        rows, total = [], 0
    else:
        board = view == 'board'
        rows, total = repo.list_filtered(conn, status=status, artisan_id=artisan_id, priority=priority,
                                         limit=None if board else limit, offset=0 if board else offset)
    items = _dtos(conn, rows, today)
    if view == 'board':
        return {'view': 'board', 'total': total,
                'columns': [{'status': s, 'items': [j for j in items if j['status'] == s]} for s in STATUSES]}
    return {'view': 'list', 'items': items, 'total': total, 'limit': limit, 'offset': offset}


def get_job(conn: sqlite3.Connection, job_id: int, tz: str) -> dict[str, Any]:
    row = _require(conn, job_id)
    dto = _dtos(conn, [row], today_local(tz))[0]
    dto['progressHistory'] = [{'id': p['id'], 'percent': p['percent'], 'note': p['note'],
                               'actorUserId': p['actor_user_id'], 'createdAt': p['created_at']}
                              for p in repo.progress_for_job(conn, job_id)]
    return dto


# --- commands ---------------------------------------------------------------------------------------------------

def create_manual(conn: sqlite3.Connection, body: JobCreate, tz: str) -> dict[str, Any]:
    """Staff creates a job for one order line, status `order_confirmed` (Req 24.2)."""
    with db.transaction(conn):
        order = orders_api.get_order(conn, body.orderId)
        if order is None:
            raise NotFound('Order not found')
        line = next((ln for ln in order['lines'] if ln['id'] == body.orderLineId), None)
        if line is None:
            raise ValidationFailed([{'field': 'orderLineId', 'reason': 'not a line of this order'}])
        job_id = repo.insert(conn, {'order_id': order['id'], 'order_line_id': line['id'],
                                    'product_id': line['productId'],
                                    'quantity': body.quantity if body.quantity is not None else line['quantity'],
                                    'is_demo': 1 if order.get('isDemo') else 0}, utc_now_iso())
    return get_job(conn, job_id, tz)


def create_jobs_for_order(conn: sqlite3.Connection, order_id: str) -> list[int]:
    """One job per order line whose product is made to order or whose quantity exceeds the stock left after the
    checkout deduction (Req 24.1, design O3). Lines that already have a job are skipped, so a repeat is harmless.
    Runs in the caller's transaction; returns the new job ids."""
    order = orders_api.get_order(conn, order_id)
    if order is None:
        return []
    lines = order['lines']
    made_to_order = products_api.made_to_order_ids(conn, [ln['productId'] for ln in lines])
    now = utc_now_iso()
    created: list[int] = []
    for line in lines:
        needs_job = (line['productId'] in made_to_order
                     or line['quantity'] > inventory_api.available_quantity(conn, line['productId'],
                                                                           line['variationId']))
        if not needs_job or repo.has_job_for_line(conn, order['id'], line['id']):
            continue
        created.append(repo.insert(conn, {'order_id': order['id'], 'order_line_id': line['id'],
                                          'product_id': line['productId'], 'quantity': line['quantity'],
                                          'is_demo': 1 if order.get('isDemo') else 0}, now))
    return created


def _parse_deadline(raw: str, tz: str) -> str:
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        raise ValidationFailed([{'field': 'deadline', 'reason': 'must be a date in YYYY-MM-DD format'}]) from None
    if len(raw) != 10:
        raise ValidationFailed([{'field': 'deadline', 'reason': 'must be a date in YYYY-MM-DD format'}])
    if parsed < today_local(tz):
        raise ValidationFailed([{'field': 'deadline', 'reason': 'must not be earlier than today'}])
    return parsed.isoformat()


def assign(conn: sqlite3.Connection, job_id: int, body: JobAssign, tz: str) -> dict[str, Any]:
    """`order_confirmed` -> `production_assigned` with artisan, quantity, deadline, priority and notes (Req 24.3)."""
    with db.transaction(conn):
        row = _require(conn, job_id)
        deadline = _parse_deadline(body.deadline, tz)
        if not artisans_api.exists(conn, body.artisanId):
            raise ValidationFailed([{'field': 'artisanId', 'reason': 'unknown artisan'}])
        if row['status'] != 'order_confirmed':
            raise Conflict('Only a job in order_confirmed can be assigned',
                           details=[{'current': row['status'], 'requested': 'production_assigned'}])
        repo.assign(conn, job_id, artisan_id=body.artisanId, quantity=body.quantity, deadline=deadline,
                    priority=body.priority, notes=body.notes, now=utc_now_iso())
    return get_job(conn, job_id, tz)


def change_status(conn: sqlite3.Connection, job_id: int, requested: str, tz: str) -> dict[str, Any]:
    """Allowed sequence only (Req 24.4); anything else is 409 naming both statuses (Req 24.5).
    Reaching `ready_for_fulfilment` notifies staff and leaves the order's Fulfilment_Status alone (Req 24.11)."""
    with db.transaction(conn):
        row = _require(conn, job_id)
        current = row['status']
        if requested not in TRANSITIONS.get(current, ()):
            raise Conflict(f'Cannot change production status from {current} to {requested}',
                           details=[{'current': current, 'requested': requested}])
        repo.set_status(conn, job_id, requested, utc_now_iso())
        if requested == 'ready_for_fulfilment':
            label = f'Production job {job_id}' + (f' for order {row["order_id"]}' if row['order_id'] else '')
            notifications_api.production_ready(conn, job_id, label)
    return get_job(conn, job_id, tz)


def add_progress(conn: sqlite3.Connection, job_id: int, body: ProgressIn, actor_user_id: int, tz: str) -> dict[str, Any]:
    with db.transaction(conn):
        _require(conn, job_id)
        repo.add_progress(conn, job_id, body.percent, body.note, actor_user_id, utc_now_iso())
    return get_job(conn, job_id, tz)
