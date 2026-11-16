"""RBAC_Guard: request dependencies for sessions and roles (Req 6.1, 6.2, 33.1)."""
from __future__ import annotations

import sqlite3
from typing import Annotated, Iterator, Optional

from fastapi import Depends, Request

from ... import db
from ...errors import Forbidden, Unauthenticated
from .service import SessionInfo, validate_session


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """One connection per request. Sync dependencies and endpoints may run in different worker threads,
    and the connection is used by one request at a time, so the same-thread check is relaxed."""
    conn = db.connect(request.app.state.settings.database_path, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


ConnDep = Annotated[sqlite3.Connection, Depends(get_conn)]


def _bearer_token(request: Request) -> Optional[str]:
    """Token from `Authorization: Bearer <token>`; None when the header is absent, raises when malformed."""
    header = request.headers.get('authorization')
    if header is None:
        return None
    parts = header.split(' ')
    if len(parts) != 2 or parts[0].lower() != 'bearer' or not parts[1].strip():
        raise Unauthenticated()
    return parts[1].strip()


def current_session(request: Request, conn: ConnDep) -> SessionInfo:
    """Required session: 401 `unauthenticated` (missing, malformed, unknown, revoked, inactive user)
    or 401 `session_expired`."""
    token = _bearer_token(request)
    if token is None:
        raise Unauthenticated()
    return validate_session(conn, token)


def optional_session(request: Request, conn: ConnDep) -> Optional[SessionInfo]:
    """Visitor-friendly variant: None without a header; a present but invalid token is still rejected."""
    token = _bearer_token(request)
    if token is None:
        return None
    return validate_session(conn, token)


SessionDep = Annotated[SessionInfo, Depends(current_session)]
OptionalSessionDep = Annotated[Optional[SessionInfo], Depends(optional_session)]


def require_roles(*roles: str):
    """Dependency factory: 401 without a valid session, 403 when the Role is not allowed."""
    allowed = frozenset(roles)

    def checker(session: SessionDep) -> SessionInfo:
        if session.role not in allowed:
            raise Forbidden()
        return session

    return checker


require_staff = require_roles('seller', 'admin')
require_admin = require_roles('admin')
require_customer = require_roles('customer')
