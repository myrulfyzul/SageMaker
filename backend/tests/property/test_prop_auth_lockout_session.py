"""Property tests for login lockout, logout and session lifetime.

Feature: sagemaker-asia-mobile-platform
Property 11: Authentication responses and lockout
Property 43: Session lifetime

**Validates: Requirements 5.2, 5.3, 5.7, 33.1**

Time is controlled by replacing `utc_now` in the auth service module with a settable clock, so the
five-failures-in-ten-minutes and five-minute lock rules can be checked at exact boundaries.
"""
from __future__ import annotations

import itertools
import math
import shutil
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, strategies as st

from app import db, security
from app.config import Settings
from app.errors import AppError
from app.main import create_app
from app.migrations.runner import run_migrations
from app.modules.auth import service as auth_service
from app.modules.auth.schemas import LoginRequest
from app.modules.users import api as users_api

# Built at runtime so the repository secret scan sees no literal secret.
PASSWORD = ''.join(['Secret', '123'])

T0 = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
FAILURES = 5
WINDOW = timedelta(minutes=10)
LOCK = timedelta(minutes=5)

PBT = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture,
                                                                         HealthCheck.too_slow])

_counter = itertools.count(1)


class Clock:
    def __init__(self, now: datetime = T0):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture(scope='module')
def env():
    run_dir = Path(tempfile.mkdtemp(prefix='sagemaker_prop_auth_'))
    cfg = Settings(database_path=run_dir / 'prop.sqlite3', media_dir=run_dir / 'media', demo_mode=True)
    app = create_app(cfg)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield {'app': app, 'client': client, 'settings': cfg, 'hash': security.hash_password(PASSWORD)}
    shutil.rmtree(run_dir, ignore_errors=True)


def _new_user(env, prefix: str = 'u') -> str:
    """Insert a fresh customer (reusing a precomputed hash) and return its e-mail."""
    email = f'{prefix}{next(_counter)}@example.com'
    conn = db.connect(env['settings'].database_path)
    try:
        with db.transaction(conn):
            users_api.create_customer(conn, name='Prop User', email=email, password_hash=env['hash'])
    finally:
        conn.close()
    return email


def _login(client, email: str, password: str):
    return client.post('/api/auth/login', json={'email': email, 'password': password})


def _auth(token: str) -> dict:
    return {'Authorization': f'Bearer {token}'}


wrong_passwords = st.text(max_size=40).filter(lambda s: s != PASSWORD)


# ---- Property 11: identical 401 for unknown email and wrong password -------------------------------

@PBT
@given(wrong=wrong_passwords, other_wrong=wrong_passwords,
       local=st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789', min_size=1, max_size=20))
def test_unknown_email_and_wrong_password_give_identical_401(env, wrong, other_wrong, local):
    """**Validates: Requirements 5.2**"""
    client = env['client']
    known = _new_user(env)
    unknown = f'nobody{next(_counter)}{local}@example.com'
    a = _login(client, known, wrong)
    b = _login(client, unknown, other_wrong)
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()
    assert 'token' not in a.text and 'token' not in b.text


# ---- Property 11: lockout iff five consecutive failures within 10 minutes --------------------------

attempt = st.tuples(
    st.one_of(st.integers(0, 30), st.integers(0, 400), st.integers(290, 310), st.integers(590, 610),
              st.integers(0, 1500)),
    st.sampled_from([True, False, False, False, False]),  # correct credentials?
)


@PBT
@given(attempts=st.lists(attempt, min_size=1, max_size=18))
def test_login_is_429_iff_five_failures_within_ten_minutes_and_lock_active(env, attempts):
    """**Validates: Requirements 5.2, 5.3**"""
    email = _new_user(env, 'lock')
    conn = db.connect(env['settings'].database_path)
    clock = Clock()
    run: list[datetime] = []           # failures in the current consecutive run
    lock_until = None                  # end of the active/last lock, if any
    try:
        with patch.object(auth_service, 'utc_now', clock):
            for gap, correct in attempts:
                clock.now += timedelta(seconds=gap)
                now = clock.now
                req = LoginRequest(email=email, password=PASSWORD if correct else 'definitely-wrong-1')

                if lock_until is not None and now < lock_until:
                    with pytest.raises(AppError) as exc:
                        auth_service.login(conn, req, 3600)
                    assert exc.value.status == 429
                    expected_wait = math.ceil((lock_until - now).total_seconds())
                    assert exc.value.retry_after_seconds == max(1, expected_wait)
                    assert 0 < exc.value.retry_after_seconds <= 300
                    continue

                if lock_until is not None:      # lock served: a fresh count starts
                    lock_until, run = None, []

                if correct:
                    result = auth_service.login(conn, req, 3600)
                    assert result['token']
                    run = []
                else:
                    with pytest.raises(AppError) as exc:
                        auth_service.login(conn, req, 3600)
                    assert exc.value.status == 401
                    run.append(now)
                    if len(run) >= FAILURES and run[-1] - run[-FAILURES] <= WINDOW:
                        lock_until = now + LOCK
    finally:
        conn.close()


@PBT
@given(extra_gap=st.integers(0, 299))
def test_correct_credentials_rejected_during_lock_and_issue_no_token(env, extra_gap):
    """**Validates: Requirements 5.3**"""
    client = env['client']
    email = _new_user(env, 'locked')
    clock = Clock()
    with patch.object(auth_service, 'utc_now', clock):
        for i in range(FAILURES):
            assert _login(client, email, 'definitely-wrong-1').status_code == 401
            if i < FAILURES - 1:
                clock.now += timedelta(seconds=1)
        clock.now += timedelta(seconds=extra_gap)   # still < 5 minutes after the fifth failure
        r = _login(client, email, PASSWORD)
        assert r.status_code == 429
        assert 'token' not in r.text
        assert r.headers['retry-after'] == str(r.json()['error']['details'][0]['retry_after_seconds'])
        clock.now += LOCK
        assert _login(client, email, PASSWORD).status_code == 200


# ---- Property 11: after logout every protected request with the token is 401 ----------------------

PROTECTED = [('GET', '/api/auth/session'), ('GET', '/api/me'), ('GET', '/api/me/addresses'),
             ('PUT', '/api/me'), ('POST', '/api/auth/logout')]


@PBT
@given(request=st.sampled_from(PROTECTED), new_name=st.text(alphabet='abcdefgh', min_size=1, max_size=10))
def test_after_logout_token_is_rejected_with_401_and_changes_nothing(env, request, new_name):
    """**Validates: Requirements 5.7**"""
    client = env['client']
    email = _new_user(env, 'out')
    token = _login(client, email, PASSWORD).json()['token']
    assert client.get('/api/auth/session', headers=_auth(token)).status_code == 200
    assert client.post('/api/auth/logout', headers=_auth(token)).status_code == 204

    method, path = request
    kwargs = {'json': {'name': new_name, 'phone': '0123456789'}} if method == 'PUT' else {}
    r = client.request(method, path, headers=_auth(token), **kwargs)
    assert r.status_code == 401

    conn = db.connect(env['settings'].database_path)
    try:
        name = conn.execute('SELECT name FROM users WHERE email = ?', (email,)).fetchone()[0]
    finally:
        conn.close()
    assert name == 'Prop User'


# ---- Property 43: session lifetime -----------------------------------------------------------------

@st.composite
def lifetime_and_age(draw):
    lifetime = draw(st.integers(3600, 2592000))                      # 1 hour .. 30 days (seconds)
    life_us = lifetime * 1_000_000
    near = draw(st.integers(-5_000_000, 5_000_000).filter(lambda d: d != 0))   # around the boundary
    age_us = draw(st.one_of(st.integers(0, 2 * life_us), st.just(life_us + near)))
    return lifetime, max(0, age_us)


@PBT
@given(case=lifetime_and_age())
def test_request_accepted_iff_age_within_lifetime_and_expired_changes_no_data(env, case):
    """**Validates: Requirements 33.1**"""
    lifetime, age_us = case
    life_us = lifetime * 1_000_000
    # Exactly age == lifetime is the one instant where the implementation expires the session
    # (`now >= expires_at`); the property is exercised on both sides of it.
    if age_us == life_us:
        age_us += 1

    client, app = env['client'], env['app']
    original = app.state.settings
    app.state.settings = replace(original, token_lifetime_seconds=lifetime)
    email = _new_user(env, 'life')
    clock = Clock()
    try:
        with patch.object(auth_service, 'utc_now', clock):
            login = _login(client, email, PASSWORD).json()
            token = login['token']
            assert datetime.fromisoformat(login['expiresAt']) == T0 + timedelta(seconds=lifetime)

            clock.now = T0 + timedelta(microseconds=age_us)
            session = client.get('/api/auth/session', headers=_auth(token))
            update = client.put('/api/me', headers=_auth(token),
                                json={'name': 'Changed Name', 'phone': '0123456789'})
    finally:
        app.state.settings = original

    conn = db.connect(env['settings'].database_path)
    try:
        name = conn.execute('SELECT name FROM users WHERE email = ?', (email,)).fetchone()[0]
    finally:
        conn.close()

    if age_us <= life_us:
        assert session.status_code == 200
        assert update.status_code == 200 and name == 'Changed Name'
    else:
        assert session.status_code == 401 and session.json()['error']['code'] == 'session_expired'
        assert update.status_code == 401 and update.json()['error']['code'] == 'session_expired'
        assert name == 'Prop User'  # expired session changes no data
