"""Auth module: registration, login lockout, sessions, expiry and the RBAC_Guard dependencies."""
from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest
from fastapi import Depends

from app import db
from app.modules.auth import service as auth_service
from app.modules.auth.deps import require_admin, require_customer, require_staff, optional_session
from app.modules.users import api as users_api
from app.security import hash_password
from app.time_utils import utc_now

PASSWORD = ''.join(['Secret', '123'])
WRONG = ''.join(['Wrong', '1234'])


def _register(client, email='a@example.com', **extra):
    return client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD, **extra})


def _login(client, email='a@example.com', password=PASSWORD):
    return client.post('/api/auth/login', json={'email': email, 'password': password})


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _db(settings):
    return db.connect(settings.database_path)


def test_register_creates_customer_and_ignores_role(client, settings):
    r = _register(client, role='admin')
    assert r.status_code == 201
    body = r.json()
    assert body['role'] == 'customer' and body['email'] == 'a@example.com'
    assert 'password' not in r.text and 'hash' not in r.text.lower()


def test_register_duplicate_email_case_insensitive_is_409(client):
    assert _register(client).status_code == 201
    r = _register(client, email='A@Example.com')
    assert r.status_code == 409
    assert 'hash' not in r.text.lower()


@pytest.mark.parametrize('payload', [
    {'name': '', 'email': 'a@example.com', 'password': PASSWORD},
    {'name': 'x', 'email': 'not-an-email', 'password': PASSWORD},
    {'name': 'x', 'email': 'a@example.com', 'password': ''.join(['sh', 'ort1'])},
    {'name': 'x', 'email': 'a@example.com', 'password': ''.join(['only', 'letters'])},
    {'name': 'x', 'email': 'a@example.com', 'password': ''.join(['1234', '5678'])},
])
def test_register_invalid_is_422_and_creates_nothing(client, settings, payload):
    r = client.post('/api/auth/register', json=payload)
    assert r.status_code == 422
    assert r.json()['error']['details']
    conn = _db(settings)
    assert conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
    conn.close()


def test_register_internal_failure_is_500_and_persists_nothing(client, settings, monkeypatch):
    def boom(*a, **k):
        raise sqlite3.OperationalError('disk I/O error')
    monkeypatch.setattr(users_api, 'create_customer', boom)
    r = client.post('/api/auth/register', json={'name': 'x', 'email': 'a@example.com', 'password': PASSWORD})
    assert r.status_code == 500 and r.json()['error']['code'] == 'registration_failed'
    conn = _db(settings)
    assert conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
    conn.close()


def test_login_session_logout_flow(client, settings):
    _register(client)
    r = _login(client)
    assert r.status_code == 200
    token = r.json()['token']
    assert r.json()['role'] == 'customer' and r.json()['expiresAt']
    conn = _db(settings)
    stored = conn.execute('SELECT token_hash FROM sessions').fetchone()[0]
    conn.close()
    assert stored != token  # only a hash is stored

    s = client.get('/api/auth/session', headers=_auth(token))
    assert s.status_code == 200 and s.json()['user']['email'] == 'a@example.com'

    assert client.post('/api/auth/logout', headers=_auth(token)).status_code == 204
    assert client.get('/api/auth/session', headers=_auth(token)).status_code == 401


def test_login_generic_401_for_unknown_and_wrong_password(client):
    _register(client)
    a = _login(client, email='nobody@example.com')
    b = _login(client, password=WRONG)
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_lockout_after_five_failures_blocks_correct_credentials(client):
    _register(client)
    for _ in range(5):
        assert _login(client, password=WRONG).status_code == 401
    r = _login(client)
    assert r.status_code == 429
    secs = r.json()['error']['details'][0]['retry_after_seconds']
    assert 0 < secs <= 300
    assert r.headers['retry-after'] == str(secs)


def test_lockout_expires_and_success_clears_failures(client, settings):
    _register(client)
    for _ in range(5):
        _login(client, password=WRONG)
    conn = _db(settings)
    old = (utc_now() - timedelta(minutes=6)).isoformat()
    conn.execute('UPDATE login_attempts SET attempted_at = ?', (old,))
    conn.close()
    assert _login(client).status_code == 200
    conn = _db(settings)
    assert conn.execute('SELECT COUNT(*) FROM login_attempts').fetchone()[0] == 0
    conn.close()


def test_four_failures_do_not_lock(client):
    _register(client)
    for _ in range(4):
        _login(client, password=WRONG)
    assert _login(client).status_code == 200


def test_missing_malformed_and_unknown_tokens_are_401(client):
    assert client.get('/api/auth/session').status_code == 401
    assert client.get('/api/auth/session', headers={'Authorization': 'Token abc'}).status_code == 401
    assert client.get('/api/auth/session', headers={'Authorization': 'Bearer'}).status_code == 401
    assert client.get('/api/auth/session', headers=_auth('nope')).status_code == 401


def test_expired_session_returns_session_expired(client, settings):
    _register(client)
    token = _login(client).json()['token']
    conn = _db(settings)
    conn.execute('UPDATE sessions SET expires_at = ?', ((utc_now() - timedelta(seconds=1)).isoformat(),))
    conn.close()
    r = client.get('/api/auth/session', headers=_auth(token))
    assert r.status_code == 401 and r.json()['error']['code'] == 'session_expired'


def test_session_lifetime_follows_settings(app, settings):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    app.state.settings = replace(settings, token_lifetime_seconds=3600)
    with TestClient(app) as c:
        _register(c)
        exp = _login(c).json()['expiresAt']
    from app.time_utils import parse_iso
    delta = parse_iso(exp) - utc_now()
    assert timedelta(minutes=59) < delta <= timedelta(hours=1)


def test_deactivated_user_session_is_rejected_and_login_refused(client, settings):
    _register(client)
    token = _login(client).json()['token']
    conn = _db(settings)
    uid = conn.execute('SELECT id FROM users').fetchone()[0]
    users_api_service = __import__('app.modules.users.service', fromlist=['x'])
    users_api_service.deactivate_user(conn, uid)
    conn.close()
    assert client.get('/api/auth/session', headers=_auth(token)).status_code == 401
    assert _login(client).status_code == 401


def test_revoke_user_sessions(client, settings):
    _register(client)
    token = _login(client).json()['token']
    conn = _db(settings)
    uid = conn.execute('SELECT id FROM users').fetchone()[0]
    with db.transaction(conn):
        from app.modules.auth import api as auth_api
        assert auth_api.revoke_user_sessions(conn, uid) == 1
    conn.close()
    assert client.get('/api/auth/session', headers=_auth(token)).status_code == 401


def test_rbac_dependencies(app, settings):
    from fastapi.testclient import TestClient
    conn = _db(settings)
    from app.migrations.runner import run_migrations
    run_migrations(settings.database_path)
    with db.transaction(conn):
        for role in ('customer', 'seller', 'admin', 'artisan'):
            users_api.create_user(conn, name=role, email=f'{role}@example.com',
                                  password_hash=hash_password(PASSWORD), role=role)
    conn.close()

    # Routes must be added before the app starts serving; reach the underlying FastAPI instance.
    inner = app.app
    @inner.get('/_t/staff')
    def _staff(s=Depends(require_staff)): return {'role': s.role}
    @inner.get('/_t/admin')
    def _admin(s=Depends(require_admin)): return {'role': s.role}
    @inner.get('/_t/customer')
    def _customer(s=Depends(require_customer)): return {'role': s.role}
    @inner.get('/_t/optional')
    def _optional(s=Depends(optional_session)): return {'role': s.role if s else None}

    expected = {
        '/_t/staff': {'seller', 'admin'},
        '/_t/admin': {'admin'},
        '/_t/customer': {'customer'},
    }
    with TestClient(app) as c:
        tokens = {r: _login(c, email=f'{r}@example.com').json()['token'] for r in ('customer', 'seller', 'admin', 'artisan')}
        for path, allowed in expected.items():
            assert c.get(path).status_code == 401
            for role, tok in tokens.items():
                got = c.get(path, headers=_auth(tok)).status_code
                assert got == (200 if role in allowed else 403), (path, role)
        assert c.get('/_t/optional').json() == {'role': None}
        assert c.get('/_t/optional', headers=_auth(tokens['admin'])).json() == {'role': 'admin'}
        assert c.get('/_t/optional', headers=_auth('bad')).status_code == 401
