"""The only surface other modules may import from `production`.

Definitions:
- an open job is one whose status is not `completed` and not `ready_for_fulfilment`;
- a completed job is one whose status is `completed` or `ready_for_fulfilment`.

Every function takes the caller's open connection and none starts or commits a transaction. The heavier imports are
done inside the functions that need them, so `orders` can call this module without an import cycle.
"""
from __future__ import annotations

import sqlite3

from . import repository as repo


def counts_for_artisan(conn: sqlite3.Connection, artisan_id: int) -> dict[str, int]:
    """`{'open': n, 'completed': m}` job counts (integers of 0 or more) for one artisan (Req 23.3)."""
    return {'open': repo.count_open_for_artisan(conn, artisan_id),
            'completed': repo.count_completed_for_artisan(conn, artisan_id)}


def open_job_ids(conn: sqlite3.Connection, artisan_id: int) -> list[int]:
    """Identifiers of the artisan's open jobs, ascending (used for the `unavailable` warning, Req 23.6)."""
    return repo.open_ids_for_artisan(conn, artisan_id)


def open_job_count(conn: sqlite3.Connection) -> int:
    """Number of open production jobs across all artisans (dashboard KPI, Req 19.2)."""
    return repo.count_open(conn)


def create_jobs_for_order(conn: sqlite3.Connection, order_id: str) -> list[int]:
    """Create `order_confirmed` jobs for the lines of a confirmed order that need production (Req 24.1).
    Returns the new job ids; lines that already have a job are skipped."""
    from . import service
    return service.create_jobs_for_order(conn, order_id)


def production_label(conn: sqlite3.Connection, order_id: str) -> str | None:
    """Customer-visible label for an order: the status of its least advanced job, or None without jobs (Req 15.10).
    Read-only; production never changes the order's Fulfilment_Status (Req 30.3)."""
    from .service import STATUSES
    statuses = [r['status'] for r in repo.latest_status_by_order(conn, order_id)]
    return min(statuses, key=STATUSES.index) if statuses else None


def production_progress(conn: sqlite3.Connection, order_id: str) -> int | None:
    """Customer-visible progress 0-100 for an order: the lowest progress among its jobs (consistent with the
    least-advanced status label), or None without jobs (Req 30.4). Read-only."""
    row = conn.execute('SELECT MIN(progress_percent) FROM production_jobs WHERE order_id = ?', (order_id,)).fetchone()
    return None if row is None or row[0] is None else int(row[0])


def assert_job_assigned_to_user(conn: sqlite3.Connection, job_id: int, user_id: int) -> None:
    """Raise Forbidden unless the job is assigned to the Artisan profile of this Artisan_User (Req 6.7, 6.8)."""
    from . import service
    service.assert_job_assigned_to_user(conn, job_id, user_id)


def create_job_for_custom_order(conn: sqlite3.Connection, custom_order_id: int, artisan_id: int, quantity: int,
                                deadline: str) -> int:
    """Create the single Production_Job linked to an accepted custom order, already `production_assigned`
    (Req 25.7). Runs in the caller's transaction so the assignment and the job persist together or not at all."""
    from app.time_utils import utc_now_iso
    now = utc_now_iso()
    job_id = repo.insert(conn, {'custom_order_id': custom_order_id, 'artisan_id': artisan_id,
                                'quantity': quantity, 'deadline': deadline}, now)
    repo.set_status(conn, job_id, 'production_assigned', now)
    return job_id


def job_summaries(conn: sqlite3.Connection, job_ids: list[int]) -> dict[int, dict]:
    """`job_id -> {'status', 'progressPercent'}` for the customer-visible production label (Req 25.9)."""
    result: dict[int, dict] = {}
    for job_id in dict.fromkeys(job_ids):
        row = repo.get(conn, job_id)
        if row is not None:
            result[int(job_id)] = {'status': row['status'], 'progressPercent': row['progress_percent']}
    return result
