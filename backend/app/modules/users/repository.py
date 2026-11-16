"""SQL for the users, addresses and favourites tables. No business rules live here."""
from __future__ import annotations

import sqlite3
from typing import Optional

# Never selected into responses: password_hash is only returned by get_auth_record.
_PUBLIC_USER_COLUMNS = 'id, name, email, phone, role, is_active, is_demo, created_at'


def insert_user(conn: sqlite3.Connection, *, name: str, email: str, email_lower: str, password_hash: str,
                phone: Optional[str], role: str, is_demo: bool, now: str) -> int:
    cur = conn.execute(
        'INSERT INTO users (name, email, email_lower, password_hash, phone, role, is_active, is_demo, created_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)',
        (name, email, email_lower, password_hash, phone, role, 1 if is_demo else 0, now, now))
    return int(cur.lastrowid)


def get_user(conn: sqlite3.Connection, user_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(f'SELECT {_PUBLIC_USER_COLUMNS} FROM users WHERE id = ?', (user_id,)).fetchone()


def get_user_by_email_lower(conn: sqlite3.Connection, email_lower: str) -> Optional[sqlite3.Row]:
    return conn.execute(f'SELECT {_PUBLIC_USER_COLUMNS} FROM users WHERE email_lower = ?', (email_lower,)).fetchone()


def get_auth_record(conn: sqlite3.Connection, email_lower: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        'SELECT id, name, email, phone, role, is_active, password_hash FROM users WHERE email_lower = ?',
        (email_lower,)).fetchone()


def update_profile(conn: sqlite3.Connection, user_id: int, name: str, phone: str, now: str) -> None:
    conn.execute('UPDATE users SET name = ?, phone = ?, updated_at = ? WHERE id = ?', (name, phone, now, user_id))


def update_role(conn: sqlite3.Connection, user_id: int, role: str, now: str) -> int:
    return conn.execute('UPDATE users SET role = ?, updated_at = ? WHERE id = ?', (role, now, user_id)).rowcount


def deactivate(conn: sqlite3.Connection, user_id: int, now: str) -> int:
    return conn.execute('UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?', (now, user_id)).rowcount


# Every address query filters on user_id, so another customer's id is indistinguishable from a missing one.
def list_addresses(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    return conn.execute('SELECT * FROM addresses WHERE user_id = ? ORDER BY is_default DESC, id ASC', (user_id,)).fetchall()


def get_address(conn: sqlite3.Connection, user_id: int, address_id: int) -> Optional[sqlite3.Row]:
    return conn.execute('SELECT * FROM addresses WHERE id = ? AND user_id = ?', (address_id, user_id)).fetchone()


def insert_address(conn: sqlite3.Connection, user_id: int, f: dict, is_default: bool, now: str) -> int:
    cur = conn.execute(
        'INSERT INTO addresses (user_id, recipient_name, phone, line1, line2, postcode, city, state, is_default, created_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (user_id, f['recipient_name'], f['phone'], f['line1'], f['line2'], f['postcode'], f['city'], f['state'],
         1 if is_default else 0, now, now))
    return int(cur.lastrowid)


def update_address(conn: sqlite3.Connection, user_id: int, address_id: int, f: dict, now: str) -> int:
    return conn.execute(
        'UPDATE addresses SET recipient_name = ?, phone = ?, line1 = ?, line2 = ?, postcode = ?, city = ?, state = ?, '
        'updated_at = ? WHERE id = ? AND user_id = ?',
        (f['recipient_name'], f['phone'], f['line1'], f['line2'], f['postcode'], f['city'], f['state'],
         now, address_id, user_id)).rowcount


def clear_default(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute('UPDATE addresses SET is_default = 0 WHERE user_id = ? AND is_default = 1', (user_id,))


def set_default(conn: sqlite3.Connection, user_id: int, address_id: int, now: str) -> int:
    return conn.execute('UPDATE addresses SET is_default = 1, updated_at = ? WHERE id = ? AND user_id = ?',
                        (now, address_id, user_id)).rowcount


def delete_address(conn: sqlite3.Connection, user_id: int, address_id: int) -> int:
    return conn.execute('DELETE FROM addresses WHERE id = ? AND user_id = ?', (address_id, user_id)).rowcount


def add_favourite(conn: sqlite3.Connection, user_id: int, product_id: str, now: str) -> int:
    return conn.execute('INSERT OR IGNORE INTO favourites (user_id, product_id, created_at) VALUES (?, ?, ?)',
                        (user_id, product_id, now)).rowcount


def remove_favourite(conn: sqlite3.Connection, user_id: int, product_id: str) -> int:
    return conn.execute('DELETE FROM favourites WHERE user_id = ? AND product_id = ?', (user_id, product_id)).rowcount


def favourite_product_ids(conn: sqlite3.Connection, user_id: int) -> list[str]:
    rows = conn.execute('SELECT product_id FROM favourites WHERE user_id = ? ORDER BY created_at DESC, product_id ASC',
                        (user_id,)).fetchall()
    return [r['product_id'] for r in rows]


def list_staff_user_ids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute("SELECT id FROM users WHERE role IN ('seller', 'admin') AND is_active = 1 ORDER BY id").fetchall()
    return [int(r['id']) for r in rows]
