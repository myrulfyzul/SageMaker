"""The only surface other modules may import from `notifications`.

Every function takes the caller's open connection and writes inside the caller's transaction, so a notification exists
exactly when the change that caused it is committed (Req 17.2, 17.3). Recipients come from `users.api`.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from app import db
from app.errors import NotFound, ValidationFailed
from app.modules.users import api as users_api
from app.time_utils import utc_now_iso

from . import repository as repo

TYPES = ('order', 'custom_order', 'low_stock', 'production', 'system')
MAX_TITLE = 100
MAX_BODY = 500


def _clip(text: str, limit: int) -> str:
    text = (text or '').strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '\u2026'


def create(conn: sqlite3.Connection, user_id: int, type: str, title: str, body: str,
           related: Optional[tuple[str, str]] = None) -> int:
    """Insert one unread notification and return its id.

    `related` is an optional `(related_type, related_id)` pair. Title and body are trimmed and clipped to 100 and 500
    characters; an empty title/body or an unknown type raises ValidationFailed (422).
    """
    if type not in TYPES:
        raise ValidationFailed([{'field': 'type', 'reason': f'must be one of {", ".join(TYPES)}'}])
    title, body = _clip(title, MAX_TITLE), _clip(body, MAX_BODY)
    if not title:
        raise ValidationFailed([{'field': 'title', 'reason': 'must not be empty'}])
    if not body:
        raise ValidationFailed([{'field': 'body', 'reason': 'must not be empty'}])
    related_type, related_id = (related[0], str(related[1])) if related else (None, None)
    return repo.insert(conn, user_id, type, title, body, related_type, related_id, utc_now_iso())


def _notify_staff(conn: sqlite3.Connection, type_: str, title: str, body: str, related: tuple[str, str]) -> list[int]:
    return [create(conn, uid, type_, title, body, related) for uid in users_api.list_staff_user_ids(conn)]


def order_created(conn: sqlite3.Connection, order_id: str, customer_user_id: Optional[int]) -> list[int]:
    """Tell the customer their order was placed and every Staff_User that a new order arrived."""
    related = ('order', order_id)
    ids: list[int] = []
    if customer_user_id is not None:
        ids.append(create(conn, customer_user_id, 'order', 'Order placed',
                          f'Your order {order_id} has been placed.', related))
    ids += _notify_staff(conn, 'order', 'New order', f'Order {order_id} was placed.', related)
    return ids


def order_status_changed(conn: sqlite3.Connection, order_id: str, customer_user_id: Optional[int],
                         previous_status: str, new_status: str) -> Optional[int]:
    """One order notification for the owner, only when the status really changed (Req 17.2, 17.4)."""
    if previous_status == new_status or customer_user_id is None:
        return None
    return create(conn, customer_user_id, 'order', 'Order update',
                  f'Your order {order_id} is now {new_status}.', ('order', order_id))


def custom_order_created(conn: sqlite3.Connection, custom_order_id: str, customer_user_id: Optional[int]) -> list[int]:
    """Tell every Staff_User that a custom order request was submitted, and acknowledge it to the customer."""
    related = ('custom_order', custom_order_id)
    ids: list[int] = []
    if customer_user_id is not None:
        ids.append(create(conn, customer_user_id, 'custom_order', 'Custom order submitted',
                          f'Your custom order request {custom_order_id} was submitted.', related))
    ids += _notify_staff(conn, 'custom_order', 'New custom order',
                         f'Custom order {custom_order_id} was submitted.', related)
    return ids


def custom_order_status_changed(conn: sqlite3.Connection, custom_order_id: str, customer_user_id: Optional[int],
                                previous_status: str, new_status: str) -> Optional[int]:
    """One custom-order notification for the owner, only when the status really changed (Req 17.3, 17.4)."""
    if previous_status == new_status or customer_user_id is None:
        return None
    return create(conn, customer_user_id, 'custom_order', 'Custom order update',
                  f'Your custom order {custom_order_id} is now {new_status}.', ('custom_order', custom_order_id))


def low_stock(conn: sqlite3.Connection, product_id: str, product_name: Optional[str] = None) -> list[int]:
    """One low-stock notification per Staff_User, skipping those with an unread one for the same product (Req 17.5)."""
    staff = users_api.list_staff_user_ids(conn)
    skip = repo.users_with_unread(conn, 'low_stock', 'product', product_id, staff)
    label = product_name or product_id
    return [create(conn, uid, 'low_stock', 'Low stock', f'{label} is at or below its low-stock threshold.',
                   ('product', product_id)) for uid in staff if uid not in skip]


def production_ready(conn: sqlite3.Connection, job_id: int | str, label: Optional[str] = None) -> list[int]:
    """Tell every Staff_User that a production job reached ready_for_fulfilment (Req 24.10)."""
    what = label or f'Production job {job_id}'
    return _notify_staff(conn, 'production', 'Production ready', f'{what} is ready for fulfilment.',
                         ('production_job', str(job_id)))


def _to_dict(row: sqlite3.Row) -> dict:
    return {'id': row['id'], 'type': row['type'], 'title': row['title'], 'body': row['body'],
            'relatedType': row['related_type'], 'relatedId': row['related_id'],
            'isRead': bool(row['is_read']), 'createdAt': row['created_at']}


def list_for_user(conn: sqlite3.Connection, user_id: int, limit: int, offset: int) -> dict:
    """The user's own notifications, newest first, with the total and the unread count (Req 17.6)."""
    rows = repo.list_for_user(conn, user_id, limit, offset)
    return {'items': [_to_dict(r) for r in rows], 'total': repo.count_for_user(conn, user_id),
            'limit': limit, 'offset': offset, 'unreadCount': repo.unread_count(conn, user_id)}


def mark_read(conn: sqlite3.Connection, user_id: int, notification_id: int) -> dict:
    """Mark one own notification read. Missing and foreign ids raise the same NotFound (Req 17.7, 17.8)."""
    with db.transaction(conn):
        if not repo.mark_read(conn, user_id, notification_id):
            raise NotFound()
    return {'unreadCount': repo.unread_count(conn, user_id)}


def mark_all_read(conn: sqlite3.Connection, user_id: int) -> dict:
    """Mark every notification of this user read; other users are untouched (Req 17.7)."""
    with db.transaction(conn):
        repo.mark_all_read(conn, user_id)
    return {'unreadCount': repo.unread_count(conn, user_id)}
