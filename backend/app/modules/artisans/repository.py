"""SQL for the `artisans` table. Only this module reads or writes that table."""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

_COLUMNS = ('id, user_id, name, specialisation, availability, story, private_phone, private_email, '
            'private_address, is_active, created_at, updated_at')


def insert(conn: sqlite3.Connection, values: dict[str, Any], now: str) -> int:
    cur = conn.execute(
        'INSERT INTO artisans (name, specialisation, availability, story, private_phone, private_email, '
        'private_address, is_active, is_demo, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)',
        (values['name'], values['specialisation'], values['availability'], values.get('story', ''),
         values.get('private_phone'), values.get('private_email'), values.get('private_address'), now, now))
    return int(cur.lastrowid)


# Column names come from this allow-list, never from the request.
_UPDATABLE = {'name', 'specialisation', 'availability', 'story', 'private_phone', 'private_email', 'private_address'}


def update(conn: sqlite3.Connection, artisan_id: int, fields: dict[str, Any], now: str) -> None:
    cols = [c for c in fields if c in _UPDATABLE]
    sets = ', '.join(f'{c} = ?' for c in cols)
    conn.execute(f'UPDATE artisans SET {sets}, updated_at = ? WHERE id = ?',
                 [fields[c] for c in cols] + [now, artisan_id])


def get(conn: sqlite3.Connection, artisan_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(f'SELECT {_COLUMNS} FROM artisans WHERE id = ?', (artisan_id,)).fetchone()


def get_active(conn: sqlite3.Connection, artisan_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(f'SELECT {_COLUMNS} FROM artisans WHERE id = ? AND is_active = 1', (artisan_id,)).fetchone()


def list_all(conn: sqlite3.Connection, *, active_only: bool, limit: int, offset: int) -> tuple[list[sqlite3.Row], int]:
    where = ' WHERE is_active = 1' if active_only else ''
    total = int(conn.execute(f'SELECT COUNT(*) FROM artisans{where}').fetchone()[0])
    rows = conn.execute(f'SELECT {_COLUMNS} FROM artisans{where} ORDER BY name COLLATE NOCASE, id LIMIT ? OFFSET ?',
                        (limit, offset)).fetchall()
    return rows, total


def get_by_user(conn: sqlite3.Connection, user_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(f'SELECT {_COLUMNS} FROM artisans WHERE user_id = ?', (user_id,)).fetchone()


def set_user(conn: sqlite3.Connection, artisan_id: int, user_id: Optional[int], now: str) -> None:
    conn.execute('UPDATE artisans SET user_id = ?, updated_at = ? WHERE id = ?', (user_id, now, artisan_id))
