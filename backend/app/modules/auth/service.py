"""Registration, login with lockout, logout and session validation (Req 4, 5, 6.1, 33.1)."""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from ... import db, security
from ...errors import AppError, Unauthenticated
from ...time_utils import parse_iso, utc_now
from ..users import api as users_api
from . import repository as repo
from .schemas import LoginRequest, RegisterRequest

LOCKOUT_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=10)
LOCKOUT_DURATION = timedelta(minutes=5)

INVALID_CREDENTIALS = 'Invalid email or password'


class RegistrationFailed(AppError):
    status = 500
    code = 'registration_failed'
    message = 'Registration failed'


class SessionExpired(Unauthenticated):
    code = 'session_expired'
    message = 'Your session has expired. Please log in again'


class TooManyAttempts(AppError):
    status = 429
    code = 'too_many_attempts'
    message = 'Too many failed login attempts. Try again later'

    def __init__(self, retry_after_seconds: int):
        super().__init__(details=[{'retry_after_seconds': retry_after_seconds}],
                         headers={'Retry-After': str(retry_after_seconds)})
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class SessionInfo:
    session_id: int
    user_id: int
    role: str
    name: str
    email: str
    expires_at: str


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _user_out(user: dict[str, Any]) -> dict[str, Any]:
    return {'id': user['id'], 'name': user['name'], 'email': user['email'], 'role': user['role']}


# ---- registration ------------------------------------------------------------------------------

def register(conn: sqlite3.Connection, data: RegisterRequest) -> dict[str, Any]:
    """Create a `customer`. Any supplied role never reaches this function (schema drops it)."""
    try:
        password_hash = security.hash_password(data.password)
        with db.transaction(conn):
            user = users_api.create_customer(conn, name=data.name, email=str(data.email), password_hash=password_hash)
    except AppError:
        raise  # 409 duplicate etc.; the transaction has been rolled back
    except Exception:
        # Rolled back by db.transaction: no partial user is persisted (Req 4.7).
        raise RegistrationFailed() from None
    return _user_out(user)


# ---- login -------------------------------------------------------------------------------------

def _lock_state(failures: list[sqlite3.Row], now: datetime) -> tuple[Optional[datetime], Optional[int]]:
    """Return (latest lock_until, index of the fifth failure of the latest 5-in-10-minutes window)."""
    times = [parse_iso(r['attempted_at']) for r in failures]
    latest_until: Optional[datetime] = None
    last_idx: Optional[int] = None
    for i in range(len(times) - LOCKOUT_FAILURES + 1):
        j = i + LOCKOUT_FAILURES - 1
        if times[j] - times[i] <= FAILURE_WINDOW:
            latest_until = times[j] + LOCKOUT_DURATION
            last_idx = j
    return latest_until, last_idx


def _lock_remaining(failures: list[sqlite3.Row], now: datetime) -> Optional[int]:
    until, _ = _lock_state(failures, now)
    if until is not None and now < until:
        return max(1, math.ceil((until - now).total_seconds()))
    return None


def login(conn: sqlite3.Connection, data: LoginRequest, token_lifetime_seconds: int) -> dict[str, Any]:
    email_lower = data.email.strip().lower()
    now = utc_now()

    record = users_api.get_auth_record(conn, data.email)
    # Always one argon2 verification (dummy hash when unknown or inactive) so timing is similar (Req 5.2).
    usable = record is not None and record['isActive']
    credentials_ok = security.verify_password(data.password, record['passwordHash'] if usable else None)

    failed = False
    result: dict[str, Any] = {}
    with db.transaction(conn):
        failures = repo.failed_attempts(conn, email_lower)
        remaining = _lock_remaining(failures, now)
        if remaining is not None:
            raise TooManyAttempts(remaining)  # no writes; correct credentials are refused too (Req 5.3)

        # A served lockout starts a fresh count, and failures outside the window are dropped.
        _, last_idx = _lock_state(failures, now)
        stale = [r['id'] for r in failures[:last_idx + 1]] if last_idx is not None else []
        stale += [r['id'] for r in failures
                  if now - parse_iso(r['attempted_at']) > FAILURE_WINDOW and r['id'] not in stale]
        if stale:
            repo.delete_attempts_by_id(conn, stale)

        if not credentials_ok:
            repo.insert_attempt(conn, email_lower, False, _iso(now))
            failed = True
        else:
            repo.delete_attempts(conn, email_lower)
            token = security.new_token()
            expires = now + timedelta(seconds=token_lifetime_seconds)
            repo.insert_session(conn, record['id'], security.hash_token(token), _iso(now), _iso(expires))
            result = {'token': token, 'expiresAt': _iso(expires), 'role': record['role'], 'user': _user_out(record)}
    if failed:
        raise Unauthenticated(INVALID_CREDENTIALS, code='invalid_credentials')
    return result


# ---- sessions ----------------------------------------------------------------------------------

def validate_session(conn: sqlite3.Connection, token: str) -> SessionInfo:
    """Resolve a bearer token. Unknown or revoked: 401 `unauthenticated`; expired: 401 `session_expired`;
    inactive user: 401 `unauthenticated` (deactivation is honoured even if sessions were not revoked)."""
    row = repo.get_session_by_hash(conn, security.hash_token(token))
    if row is None or not security.tokens_equal(row['token_hash'], security.hash_token(token)):
        raise Unauthenticated()
    if row['revoked_at'] is not None:
        raise Unauthenticated()
    if utc_now() >= parse_iso(row['expires_at']):
        raise SessionExpired()
    user = users_api.get_account(conn, row['user_id'])
    if user is None or not user['isActive']:
        raise Unauthenticated()
    return SessionInfo(session_id=row['id'], user_id=user['id'], role=user['role'], name=user['name'],
                       email=user['email'], expires_at=row['expires_at'])


def logout(conn: sqlite3.Connection, session_id: int) -> None:
    with db.transaction(conn):
        repo.revoke_session(conn, session_id, utc_now().isoformat())


def revoke_user_sessions(conn: sqlite3.Connection, user_id: int) -> int:
    """Revoke every live session of a user. Runs in the caller's transaction (used on deactivation)."""
    return repo.revoke_user_sessions(conn, user_id, utc_now().isoformat())
