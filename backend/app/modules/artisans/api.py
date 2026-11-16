"""The only surface other modules may import from `artisans`. Kept free of imports from other feature modules
that depend on it, so `products` can call it without an import cycle."""
from __future__ import annotations

import sqlite3
from typing import Optional

from . import repository as repo


def exists(conn: sqlite3.Connection, artisan_id: int) -> bool:
    """True when the artisan row exists (validates a product's artisan link, Req 20.1)."""
    return repo.get(conn, artisan_id) is not None


def is_active(conn: sqlite3.Connection, artisan_id: int) -> bool:
    """True when the artisan exists and is active (custom-order assignment, Req 25.7, 25.8)."""
    return repo.get_active(conn, artisan_id) is not None


def public_name(conn: sqlite3.Connection, artisan_id: Optional[int]) -> Optional[str]:
    """Public name of an active artisan, or None. Never returns private fields (Req 23.5)."""
    if artisan_id is None:
        return None
    row = repo.get_active(conn, artisan_id)
    return row['name'] if row is not None else None


def artisan_id_for_user(conn: sqlite3.Connection, user_id: int) -> Optional[int]:
    """Id of the Artisan profile that belongs to an Artisan_User, or None (Req 6.7)."""
    row = repo.get_by_user(conn, user_id)
    return int(row['id']) if row is not None else None


def link_user(conn: sqlite3.Connection, artisan_id: int, user_id: Optional[int]) -> None:
    """Attach (or with None detach) the login user of an artisan profile. Runs in the caller's transaction."""
    from app.time_utils import utc_now_iso
    repo.set_user(conn, artisan_id, user_id, utc_now_iso())


def names(conn: sqlite3.Connection, artisan_ids: list[int]) -> dict[int, str]:
    """`id -> name` for existing artisans (staff-facing labels; never private contact fields)."""
    result: dict[int, str] = {}
    for artisan_id in dict.fromkeys(artisan_ids):
        row = repo.get(conn, artisan_id)
        if row is not None:
            result[int(artisan_id)] = row['name']
    return result
