"""SQL for `sessions` and `login_attempts`. No business rules live here."""
from __future__ import annotations

import sqlite3
from typing import Optional


def insert_session(conn: sqlite3.Connection, user_id: int, token_hash: str, created_at: str, expires_at: str) -> int:
    cur = conn.execute(
        'INSERT INTO sessions (user_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?)',
        (user_id, token_hash, created_at, expires_at))
    return int(cur.lastrowid)


def get_session_by_hash(conn: sqlite3.Connection, token_hash: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        'SELECT id, user_id, token_hash, created_at, expires_at, revoked_at FROM sessions WHERE token_hash = ?',
        (token_hash,)).fetchone()


def revoke_session(conn: sqlite3.Connection, session_id: int, now: str) -> int:
    return conn.execute('UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL',
                        (now, session_id)).rowcount


def revoke_user_sessions(conn: sqlite3.Connection, user_id: int, now: str) -> int:
    return conn.execute('UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL',
                        (now, user_id)).rowcount


def failed_attempts(conn: sqlite3.Connection, email_lower: str) -> list[sqlite3.Row]:
    return conn.execute(
        'SELECT id, attempted_at FROM login_attempts WHERE email_lower = ? AND succeeded = 0 ORDER BY id ASC',
        (email_lower,)).fetchall()


def insert_attempt(conn: sqlite3.Connection, email_lower: str, succeeded: bool, now: str) -> None:
    conn.execute('INSERT INTO login_attempts (email_lower, succeeded, attempted_at) VALUES (?, ?, ?)',
                 (email_lower, 1 if succeeded else 0, now))


def delete_attempts(conn: sqlite3.Connection, email_lower: str) -> None:
    conn.execute('DELETE FROM login_attempts WHERE email_lower = ?', (email_lower,))


def delete_attempts_by_id(conn: sqlite3.Connection, ids: list[int]) -> None:
    conn.executemany('DELETE FROM login_attempts WHERE id = ?', [(i,) for i in ids])
