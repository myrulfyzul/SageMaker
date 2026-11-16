"""SQL for the custom-order tables: `custom_orders` and `custom_order_images`. All input is bound as parameters."""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

_COLUMNS = ('id, user_id, product_type, description, quantity, preferred_date, status, estimated_price_sen, '
            'reject_reason, artisan_id, production_job_id, is_demo, created_at, updated_at')


def insert(conn: sqlite3.Connection, user_id: int, product_type: str, description: str, quantity: int,
           preferred_date: str, is_demo: int, now: str) -> int:
    cur = conn.execute(
        'INSERT INTO custom_orders (user_id, product_type, description, quantity, preferred_date, status, '
        "is_demo, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'submitted', ?, ?, ?)",
        (user_id, product_type, description, quantity, preferred_date, is_demo, now, now))
    return int(cur.lastrowid)


def insert_image(conn: sqlite3.Connection, custom_order_id: int, filename: str, content_type: str,
                 size_bytes: int) -> None:
    conn.execute('INSERT INTO custom_order_images (custom_order_id, filename, content_type, size_bytes) '
                 'VALUES (?, ?, ?, ?)', (custom_order_id, filename, content_type, size_bytes))


def get(conn: sqlite3.Connection, custom_order_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(f'SELECT {_COLUMNS} FROM custom_orders WHERE id = ?', (custom_order_id,)).fetchone()


def get_owned(conn: sqlite3.Connection, custom_order_id: int, user_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(f'SELECT {_COLUMNS} FROM custom_orders WHERE id = ? AND user_id = ?',
                        (custom_order_id, user_id)).fetchone()


def list_filtered(conn: sqlite3.Connection, *, user_id: Optional[int], status: Optional[str], limit: int,
                  offset: int) -> tuple[list[sqlite3.Row], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if user_id is not None:
        clauses.append('user_id = ?')
        params.append(user_id)
    if status is not None:
        clauses.append('status = ?')
        params.append(status)
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    total = int(conn.execute(f'SELECT COUNT(*) FROM custom_orders{where}', params).fetchone()[0])
    rows = conn.execute(f'SELECT {_COLUMNS} FROM custom_orders{where} ORDER BY created_at DESC, id DESC '
                        'LIMIT ? OFFSET ?', params + [limit, offset]).fetchall()
    return rows, total


def images_for(conn: sqlite3.Connection, custom_order_ids: list[int]) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {i: [] for i in custom_order_ids}
    for cid in custom_order_ids:
        rows = conn.execute('SELECT filename FROM custom_order_images WHERE custom_order_id = ? ORDER BY id',
                            (cid,)).fetchall()
        result[cid] = [r['filename'] for r in rows]
    return result


def image_by_filename(conn: sqlite3.Connection, filename: str) -> Optional[sqlite3.Row]:
    """The image row joined with its owner, or None."""
    return conn.execute(
        'SELECT i.filename, i.content_type, o.user_id AS owner_id FROM custom_order_images i '
        'JOIN custom_orders o ON o.id = i.custom_order_id WHERE i.filename = ?', (filename,)).fetchone()


def set_accepted(conn: sqlite3.Connection, custom_order_id: int, price_sen: int, now: str) -> None:
    conn.execute("UPDATE custom_orders SET status = 'accepted', estimated_price_sen = ?, updated_at = ? WHERE id = ?",
                 (price_sen, now, custom_order_id))


def set_rejected(conn: sqlite3.Connection, custom_order_id: int, reason: str, now: str) -> None:
    conn.execute("UPDATE custom_orders SET status = 'rejected', reject_reason = ?, updated_at = ? WHERE id = ?",
                 (reason, now, custom_order_id))


def set_status(conn: sqlite3.Connection, custom_order_id: int, status: str, now: str) -> None:
    conn.execute('UPDATE custom_orders SET status = ?, updated_at = ? WHERE id = ?', (status, now, custom_order_id))


def set_assignment(conn: sqlite3.Connection, custom_order_id: int, artisan_id: int, job_id: int, now: str) -> None:
    conn.execute('UPDATE custom_orders SET artisan_id = ?, production_job_id = ?, updated_at = ? WHERE id = ?',
                 (artisan_id, job_id, now, custom_order_id))
