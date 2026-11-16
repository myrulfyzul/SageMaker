"""The only surface other modules may import from `auth`."""
from __future__ import annotations

import sqlite3

from . import service
from .service import SessionInfo


def validate_session(conn: sqlite3.Connection, token: str) -> SessionInfo:
    return service.validate_session(conn, token)


def revoke_user_sessions(conn: sqlite3.Connection, user_id: int) -> int:
    """Revoke all live sessions of a user inside the caller's open transaction."""
    return service.revoke_user_sessions(conn, user_id)
