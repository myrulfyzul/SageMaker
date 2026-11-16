"""SQL for the notifications table. No business rules live here."""
from __future__ import annotations

import sqlite3
from typing import Iterable, Optional


def insert(conn: sqlite3.Connection, user_id: int, type_: str, title: str, body: str,
           related_type: Optional[str], related_id: Optional[str], now: str) -> int:
    cur = conn.execute(
        'INSERT INTO notifications (user_id, type, title, body, related_type, related_id, is_read, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, 0, ?)',
        (user_id, type_, title, body, related_type, related_id, now))
    return int(cur.lastrowid)


def users_with_unread(conn: sqlite3.Connection, type_: str, related_type: str, related_id: str,
                      user_ids: Iterable[int]) -> set[int]:
    """Subset of `user_ids` that already hold an unread notification of this type for the related entity."""
    ids = list(user_ids)
    if not ids:
        return set()
    marks = ','.join('?' for _ in ids)
    rows = conn.execute(
        f'SELECT DISTINCT user_id FROM notifications WHERE type = ? AND related_type = ? AND related_id = ? '
        f'AND is_read = 0 AND user_id IN ({marks})', (type_, related_type, related_id, *ids)).fetchall()
    return {int(r['user_id']) for r in rows}


def get(conn: sqlite3.Connection, notification_id: int) -> Optional[sqlite3.Row]:
    return conn.execute('SELECT * FROM notifications WHERE id = ?', (notification_id,)).fetchone()


def list_for_user(conn: sqlite3.Connection, user_id: int, limit: int, offset: int) -> list[sqlite3.Row]:
    return conn.execute(
        'SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?',
        (user_id, limit, offset)).fetchall()


def count_for_user(conn: sqlite3.Connection, user_id: int) -> int:
    return int(conn.execute('SELECT COUNT(*) FROM notifications WHERE user_id = ?', (user_id,)).fetchone()[0])


def unread_count(conn: sqlite3.Connection, user_id: int) -> int:
    return int(conn.execute('SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0',
                            (user_id,)).fetchone()[0])


def mark_read(conn: sqlite3.Connection, user_id: int, notification_id: int) -> bool:
    """Set the read flag on one notification of this user; False when no such row exists for the user."""
    cur = conn.execute('UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?',
                       (notification_id, user_id))
    return cur.rowcount > 0


def mark_all_read(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0', (user_id,))
