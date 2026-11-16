"""SQLite access: connection factory and write transactions."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Union

BUSY_TIMEOUT_MS = 5000


def connect(path: Union[str, Path], *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open a connection in manual-transaction mode with foreign keys enforced."""
    target = Path(path)
    if str(path) != ':memory:':
        target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, timeout=BUSY_TIMEOUT_MS / 1000,
                           check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute(f'PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}')
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE ... COMMIT; ROLLBACK on any exception, including BaseException."""
    conn.execute('BEGIN IMMEDIATE')
    try:
        yield conn
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    else:
        try:
            conn.execute('COMMIT')
        except BaseException:
            if conn.in_transaction:
                conn.execute('ROLLBACK')
            raise
