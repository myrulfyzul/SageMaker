"""Unit tests for the cross-cutting backend components."""
import logging
import sqlite3

import pytest
from fastapi import HTTPException
from hypothesis import given, strategies as st
from pydantic import BaseModel

from app.config import ConfigError, Settings
from app.db import connect, transaction
from app.errors import Conflict
from app.logging_setup import redact
from app.main import create_app
from app.money import div_round_half_up, format_rm
from app.pagination import Page, PageDep
from app.time_utils import month_bucket


def env(**kw):
    return {'DATABASE_PATH': 'x.sqlite3', **kw}


# --- config ---
def test_missing_database_path_names_variable():
    with pytest.raises(ConfigError) as e:
        Settings.from_env({})
    assert e.value.variable == 'DATABASE_PATH'


@pytest.mark.parametrize('name,value', [
    ('TOKEN_LIFETIME_SECONDS', '10'), ('TOKEN_LIFETIME_SECONDS', 'abc'),
    ('ALLOWED_ORIGINS', 'localhost:5353'), ('ALLOWED_ORIGINS', 'http://a.com/path'),
    ('APP_TIMEZONE', 'Mars/Base'),
])
def test_invalid_values_name_variable(name, value):
    with pytest.raises(ConfigError) as e:
        Settings.from_env(env(**{name: value}))
    assert e.value.variable == name


def test_defaults_and_demo_mode_strictness():
    s = Settings.from_env(env())
    assert s.allowed_origins == () and s.token_lifetime_seconds == 604800 and s.demo_mode is False
    assert Settings.from_env(env(DEMO_MODE='1')).demo_mode is True
    assert Settings.from_env(env(DEMO_MODE='true')).demo_mode is False


# --- db ---
def test_transaction_commits_and_rolls_back(tmp_path):
    conn = connect(tmp_path / 'a.sqlite3')
    assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
    conn.execute('CREATE TABLE t (v INTEGER)')
    with transaction(conn):
        conn.execute('INSERT INTO t VALUES (1)')
    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute('INSERT INTO t VALUES (2)')
            raise RuntimeError('boom')
    assert [r[0] for r in conn.execute('SELECT v FROM t')] == [1]
    conn.close()


# --- money / time / logging ---
@given(st.integers(0, 10**9), st.integers(1, 10**4))
def test_div_round_half_up_matches_exact(n, d):
    from fractions import Fraction
    import math
    assert div_round_half_up(n, d) == math.floor(Fraction(n, d) + Fraction(1, 2))


def test_format_rm_and_month_bucket():
    assert format_rm(1250) == 'RM 12.50'
    assert month_bucket('2025-01-31T17:00:00+00:00', 'Asia/Kuala_Lumpur') == '2025-02'


def test_redaction():
    import secrets
    value = secrets.token_hex(8)  # generated at runtime, never a stored literal
    assert value not in redact(f"login password={value} token: '{value}' Bearer {value}")


# --- app ---
@pytest.fixture()
def local_client(tmp_path):
    from fastapi.testclient import TestClient
    s = Settings(database_path=tmp_path / 'd.sqlite3', allowed_origins=('http://ok.test',), demo_mode=True)
    app = create_app(s)
    inner = app.app

    class Body(BaseModel):
        n: int

    @inner.post('/api/_t/body')
    def body(b: Body):
        return b

    @inner.get('/api/_t/page', response_model=Page[int])
    def page(p: PageDep):
        return Page.build([], 0, p)

    @inner.get('/api/_t/conflict')
    def conflict():
        raise Conflict('nope', code='x_conflict')

    @inner.get('/api/_t/http')
    def http():
        raise HTTPException(status_code=418, detail='teapot')

    @inner.get('/api/_t/boom')
    def boom():
        raise sqlite3.IntegrityError('SELECT secret FROM users /path/file.py')

    return TestClient(app, raise_server_exceptions=False)


def test_health_docs_and_nosniff(local_client):
    r = local_client.get('/api/health')
    assert r.status_code == 200 and r.json() == {'ok': True, 'service': 'sagemaker-prototype', 'demoMode': True}
    assert r.headers['x-content-type-options'] == 'nosniff'
    assert local_client.get('/docs').status_code == 200
    assert local_client.get('/openapi.json').status_code == 200


def test_cors_allow_list(local_client):
    ok = local_client.get('/api/health', headers={'Origin': 'http://ok.test'})
    assert ok.headers['access-control-allow-origin'] == 'http://ok.test'
    bad = local_client.get('/api/health', headers={'Origin': 'http://evil.test'})
    assert 'access-control-allow-origin' not in bad.headers


def test_validation_envelope(local_client):
    r = local_client.post('/api/_t/body', json={'n': 'x'})
    err = r.json()['error']
    assert r.status_code == 422 and err['code'] == 'validation_error'
    assert err['details'][0]['field'] == 'n' and err['details'][0]['reason']


@pytest.mark.parametrize('q', ['limit=0', 'limit=101', 'offset=-1', 'offset=a'])
def test_invalid_page_params(local_client, q):
    r = local_client.get(f'/api/_t/page?{q}')
    assert r.status_code == 422 and r.json()['error']['details'][0]['field'] in ('limit', 'offset')


def test_page_envelope_defaults(local_client):
    assert local_client.get('/api/_t/page').json() == {'items': [], 'total': 0, 'limit': 20, 'offset': 0}


def test_app_error_and_http_error(local_client):
    r = local_client.get('/api/_t/conflict')
    assert r.status_code == 409 and r.json() == {'error': {'code': 'x_conflict', 'message': 'nope'}}
    assert local_client.get('/api/_t/http').status_code == 418
    assert local_client.get('/api/missing').json()['error']['code'] == 'not_found'


def test_unexpected_exception_is_generic_and_nosniff(local_client, caplog):
    with caplog.at_level(logging.ERROR):
        r = local_client.get('/api/_t/boom')
    assert r.status_code == 500
    assert r.json() == {'error': {'code': 'internal_error', 'message': 'An unexpected error occurred'}}
    assert r.headers['x-content-type-options'] == 'nosniff'
    assert 'IntegrityError' not in r.text and 'SELECT' not in r.text


def test_conftest_fixture_client(client):
    assert client.get('/api/health').status_code == 200
