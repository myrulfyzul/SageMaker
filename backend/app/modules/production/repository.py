"""SQL for the production-owned tables: `production_jobs` and `production_progress`.
All external input is bound as parameters; column names come from fixed lists."""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

# A job is "completed" once it reaches either of these; every other status is "open".
DONE_STATUSES = ('completed', 'ready_for_fulfilment')
_DONE_SQL = "('completed','ready_for_fulfilment')"

_COLUMNS = ('id, order_id, order_line_id, custom_order_id, product_id, artisan_id, quantity, deadline, priority, '
            'status, progress_percent, notes, is_demo, created_at, updated_at')


def insert(conn: sqlite3.Connection, values: dict[str, Any], now: str) -> int:
    cur = conn.execute(
        'INSERT INTO production_jobs (order_id, order_line_id, custom_order_id, product_id, artisan_id, quantity, '
        'deadline, priority, status, progress_percent, notes, is_demo, created_at, updated_at) '
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'normal', 'order_confirmed', 0, '', ?, ?, ?)",
        (values.get('order_id'), values.get('order_line_id'), values.get('custom_order_id'), values.get('product_id'),
         values.get('artisan_id'), values.get('quantity'), values.get('deadline'), int(values.get('is_demo', 0)),
         now, now))
    return int(cur.lastrowid)


def get(conn: sqlite3.Connection, job_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(f'SELECT {_COLUMNS} FROM production_jobs WHERE id = ?', (job_id,)).fetchone()


def has_job_for_line(conn: sqlite3.Connection, order_id: str, order_line_id: int) -> bool:
    return conn.execute('SELECT 1 FROM production_jobs WHERE order_id = ? AND order_line_id = ? LIMIT 1',
                        (order_id, order_line_id)).fetchone() is not None


def list_filtered(conn: sqlite3.Connection, *, status: Optional[str], artisan_id: Optional[int],
                  priority: Optional[str], limit: Optional[int], offset: int) -> tuple[list[sqlite3.Row], int]:
    """Filters are AND-combined; `limit=None` returns every match (board view)."""
    clauses: list[str] = []
    params: list[Any] = []
    for column, value in (('status', status), ('artisan_id', artisan_id), ('priority', priority)):
        if value is not None:
            clauses.append(f'{column} = ?')
            params.append(value)
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    total = int(conn.execute(f'SELECT COUNT(*) FROM production_jobs{where}', params).fetchone()[0])
    sql = f'SELECT {_COLUMNS} FROM production_jobs{where} ORDER BY id DESC'
    if limit is not None:
        sql += ' LIMIT ? OFFSET ?'
        params = params + [limit, offset]
    return conn.execute(sql, params).fetchall(), total


def assign(conn: sqlite3.Connection, job_id: int, *, artisan_id: int, quantity: int, deadline: str, priority: str,
           notes: str, now: str) -> None:
    conn.execute("UPDATE production_jobs SET artisan_id = ?, quantity = ?, deadline = ?, priority = ?, notes = ?, "
                 "status = 'production_assigned', updated_at = ? WHERE id = ?",
                 (artisan_id, quantity, deadline, priority, notes, now, job_id))


def set_status(conn: sqlite3.Connection, job_id: int, status: str, now: str) -> None:
    conn.execute('UPDATE production_jobs SET status = ?, updated_at = ? WHERE id = ?', (status, now, job_id))


def add_progress(conn: sqlite3.Connection, job_id: int, percent: int, note: str, actor_user_id: Optional[int],
                 now: str) -> None:
    conn.execute('INSERT INTO production_progress (job_id, percent, note, actor_user_id, created_at) '
                 'VALUES (?, ?, ?, ?, ?)', (job_id, percent, note, actor_user_id, now))
    conn.execute('UPDATE production_jobs SET progress_percent = ?, updated_at = ? WHERE id = ?',
                 (percent, now, job_id))


def progress_for_job(conn: sqlite3.Connection, job_id: int) -> list[sqlite3.Row]:
    return conn.execute('SELECT id, percent, note, actor_user_id, created_at FROM production_progress '
                        'WHERE job_id = ? ORDER BY id', (job_id,)).fetchall()


def latest_status_by_order(conn: sqlite3.Connection, order_id: str) -> list[sqlite3.Row]:
    return conn.execute('SELECT id, status FROM production_jobs WHERE order_id = ? ORDER BY id', (order_id,)).fetchall()


def count_open_for_artisan(conn: sqlite3.Connection, artisan_id: int) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM production_jobs WHERE artisan_id = ? AND status NOT IN {_DONE_SQL}',
                            (artisan_id,)).fetchone()[0])


def count_completed_for_artisan(conn: sqlite3.Connection, artisan_id: int) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM production_jobs WHERE artisan_id = ? AND status IN {_DONE_SQL}',
                            (artisan_id,)).fetchone()[0])


def open_ids_for_artisan(conn: sqlite3.Connection, artisan_id: int) -> list[int]:
    rows = conn.execute(f'SELECT id FROM production_jobs WHERE artisan_id = ? AND status NOT IN {_DONE_SQL} '
                        'ORDER BY id', (artisan_id,)).fetchall()
    return [int(r['id']) for r in rows]


def count_open(conn: sqlite3.Connection) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM production_jobs WHERE status NOT IN {_DONE_SQL}').fetchone()[0])
