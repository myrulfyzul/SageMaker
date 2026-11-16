"""Property 8: Secrets are never exposed or stored in clear.

**Validates: Requirements 4.2, 4.6, 5.4, 33.5**

Passwords are assembled at runtime with ''.join so the repository secret scan never sees a literal.
"""
from __future__ import annotations

import itertools
import logging
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, strategies as st

from app import security
from app.config import Settings
from app.logging_setup import configure_logging
from app.main import create_app

_LETTERS = st.text(alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=6, max_size=24)
_DIGITS = st.text(alphabet='0123456789', min_size=3, max_size=8)
_TAIL = st.text(alphabet='abcXYZ789!#$%^&*_-', min_size=0, max_size=16)


@st.composite
def passwords(draw):
    """Valid passwords (>= 8 chars, a letter and a digit), built from parts, never a literal."""
    return ''.join([draw(_LETTERS), draw(_DIGITS), draw(_TAIL)])


@settings(max_examples=15, deadline=None)
@given(pw=passwords())
def test_hash_is_salted_verifies_and_hides_password(pw):
    h1, h2 = security.hash_password(pw), security.hash_password(pw)
    assert h1 != h2  # per-hash salt
    assert pw not in h1 and pw not in h2
    assert security.verify_password(pw, h1) and security.verify_password(pw, h2)
    assert not security.verify_password(pw + 'x', h1)


@settings(max_examples=100, deadline=None)
@given(n=st.integers(min_value=0, max_value=10_000))
def test_issued_token_is_stored_only_as_sha256_hash(n):
    token = security.new_token()
    digest = security.hash_token(token)
    assert len(digest) == 64 and int(digest, 16) >= 0
    assert digest != token and token not in digest
    assert security.tokens_equal(digest, security.hash_token(token))


@pytest.fixture(scope='module')
def env():
    root = Path(tempfile.mkdtemp(prefix='sagemaker_prop_secrets_'))
    cfg = Settings(database_path=root / 'db.sqlite3', media_dir=root / 'media', demo_mode=True)
    app = create_app(cfg)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, cfg
    shutil.rmtree(root, ignore_errors=True)


_counter = itertools.count()


@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pw=passwords())
def test_no_response_log_or_db_row_exposes_secrets(env, caplog, pw):
    client, cfg = env
    configure_logging(logging.DEBUG)
    caplog.set_level(logging.DEBUG)
    email = f'user{next(_counter)}@example.com'

    reg = client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': pw})
    assert reg.status_code == 201
    bad = client.post('/api/auth/login', json={'email': email, 'password': pw + 'zz'})
    login = client.post('/api/auth/login', json={'email': email, 'password': pw})
    assert login.status_code == 200
    token = login.json()['token']
    headers = {'Authorization': f'Bearer {token}'}
    sess = client.get('/api/auth/session', headers=headers)
    out = client.post('/api/auth/logout', headers=headers)
    after = client.get('/api/auth/session', headers=headers)

    conn = sqlite3.connect(cfg.database_path)
    try:
        pw_hash = conn.execute('SELECT password_hash FROM users WHERE lower(email) = ?', (email,)).fetchone()[0]
        stored = [r[0] for r in conn.execute('SELECT token_hash FROM sessions')]
    finally:
        conn.close()

    # stored values: salted hash of the password; only the SHA-256 of the token
    assert pw_hash.startswith('$argon2') and pw not in pw_hash
    assert security.verify_password(pw, pw_hash)
    assert security.hash_token(token) in stored and token not in stored

    # responses never carry the password or hash; only login returns the token itself
    for r in (reg, bad, login, sess, out, after):
        assert pw not in r.text and pw_hash not in r.text
        assert security.hash_token(token) not in r.text
    for r in (reg, bad, sess, out, after):
        assert token not in r.text

    # log records at every level never contain any secret
    for secret in (pw, pw_hash, token, security.hash_token(token)):
        assert secret not in caplog.text
        assert all(secret not in rec.getMessage() for rec in caplog.records)
