"""The only surface other modules (checkout) may import from `cart`. Functions take the caller's open connection."""
from __future__ import annotations

import sqlite3
from typing import Any

from . import service


def load_lines(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    """Server-priced cart (`lines`, `subtotalSen`, `deliveryFeeSen`, `grandTotalSen`); lines carry `available`."""
    return service.view(conn, user_id)


def clear(conn: sqlite3.Connection, user_id: int) -> None:
    """Empty the user's cart inside the caller's transaction."""
    service.clear(conn, user_id)
