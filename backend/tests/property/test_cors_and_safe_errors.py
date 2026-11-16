"""Property tests 6 and 42: CORS allow-list and safe error responses.
Feature: sagemaker-asia-mobile-platform
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings as hsettings, strategies as st

from app.config import Settings
from app.db import connect, transaction
from app.main import create_app

# ---------------------------------------------------------------- Property 6

_hosts = st.from_regex(r'[a-z][a-z0-9]{0,10}(\.[a-z][a-z0-9]{0,10}){0,2}', fullmatch=True)
_origins = st.builds(
    lambda scheme, host, port: f'{scheme}://{host}' + (f':{port}' if port else ''),
    st.sampled_from(['http', 'https']), _hosts, st.one_of(st.none(), st.integers(1, 65535)),
)


def _cors_client(allowed: list[str]) -> TestClient:
    # No `with`: lifespan (migrations) is skipped; /api/health needs no database.
    s = Settings(database_path=Path(tempfile.gettempdir()) / 'unused_cors.sqlite3', allowed_origins=tuple(allowed))
    return TestClient(create_app(s), raise_server_exceptions=False)


@hsettings(max_examples=60, deadline=None)
@given(allowed=st.lists(_origins, max_size=4), origin=_origins, use_allowed=st.booleans())
def test_property_6_cors_allow_list(allowed, origin, use_allowed):
    """**Validates: Requirements 2.7, 2.8**"""
    if use_allowed and allowed:
        origin = allowed[0]
    client = _cors_client(allowed)
    expected = origin in allowed

    simple = client.get('/api/health', headers={'Origin': origin})
    assert ('access-control-allow-origin' in simple.headers) == expected
    if expected:
        assert simple.headers['access-control-allow-origin'] == origin

    preflight = client.options('/api/health', headers={
        'Origin': origin, 'Access-Control-Request-Method': 'GET'})
    assert ('access-control-allow-origin' in preflight.headers) == expected


# --------------------------------------------------------------- Property 42

_state: dict = {}


@pytest.fixture(scope='module')
def boom_client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp('boom') / 'boom.sqlite3'
    conn = connect(db_path)
    conn.execute('CREATE TABLE t (v TEXT)')
    app = create_app(Settings(database_path=db_path))

    def boom():
        w = connect(db_path)
        try:
            with transaction(w) as tx:
                tx.execute("INSERT INTO t VALUES ('uncommitted')")
                raise _state['exc']
        finally:
            w.close()

    app.app.add_api_route('/api/_boom', boom, methods=['GET'])
    client = TestClient(app, raise_server_exceptions=False)
    yield client, conn
    conn.close()


_idents = st.from_regex(r'[A-Za-z][A-Za-z0-9]{3,16}', fullmatch=True)


@hsettings(max_examples=50, deadline=None)
@given(name=_idents, text=st.text(max_size=40), sql=st.booleans())
def test_property_42_safe_error_responses(boom_client, name, text, sql):
    """**Validates: Requirements 28.4, 33.2**"""
    client, conn = boom_client
    cls_name = 'Zq' + name
    base = sqlite3.DatabaseError if sql else Exception
    message = f'SELECT secret FROM users C:\\srv\\app\\secret.py /etc/passwd {text}'
    _state['exc'] = type(cls_name, (base,), {})(message)

    resp = client.get('/api/_boom')

    assert resp.status_code == 500
    body = resp.text
    assert resp.json() == {'error': {'code': 'internal_error', 'message': 'An unexpected error occurred'}}
    for leaked in (cls_name, 'Traceback', 'SELECT', 'secret.py', '/etc/passwd', 'File "', 'sqlite3', '.py'):
        assert leaked not in body
    assert resp.headers['x-content-type-options'] == 'nosniff'
    # Uncommitted change rolled back.
    assert conn.execute('SELECT COUNT(*) FROM t').fetchone()[0] == 0


@hsettings(max_examples=20, deadline=None)
@given(path=st.sampled_from(['/api/health', '/api/missing', '/nope', '/docs']),
       method=st.sampled_from(['GET', 'POST', 'DELETE']))
def test_property_42_nosniff_on_every_response(boom_client, path, method):
    """**Validates: Requirements 28.4, 33.2**"""
    client, _ = boom_client
    resp = client.request(method, path)
    assert resp.headers['x-content-type-options'] == 'nosniff'
