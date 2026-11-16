"""Property 52 (product part): Product validators.

**Validates: Requirements 20.1, 20.2, 20.7**

For any product input, creation or update succeeds and reads back the same values if and only if all fields are
within their documented ranges (name 1-200, description at most 2000, price 1-99,999,999 sen, stock and threshold
0-999,999); otherwise the request is rejected with 422 identifying each invalid field and data is unchanged.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])
MAX_PRICE = 99_999_999
MAX_STOCK = 999_999

_ALPHA = st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))

names = st.one_of(
    st.text(_ALPHA, min_size=1, max_size=200),
    st.just(''),
    st.integers(201, 260).map(lambda n: 'n' * n),
)
descriptions = st.one_of(
    st.text(max_size=2000),
    st.integers(2001, 2100).map(lambda n: 'd' * n),
)
prices = st.one_of(
    st.integers(1, MAX_PRICE),
    st.sampled_from([1, MAX_PRICE, 0, MAX_PRICE + 1]),
    st.integers(-1000, 0),
    st.integers(MAX_PRICE + 1, MAX_PRICE * 3),
)
counts = st.one_of(
    st.integers(0, MAX_STOCK),
    st.sampled_from([0, MAX_STOCK, -1, MAX_STOCK + 1]),
    st.integers(-1000, -1),
    st.integers(MAX_STOCK + 1, MAX_STOCK * 3),
)


def _bad_name(v):
    return not (1 <= len(v.strip()) <= 200)


def _bad_price(v):
    return not (1 <= v <= MAX_PRICE)


def _bad_count(v):
    return not (0 <= v <= MAX_STOCK)


@pytest.fixture(scope='module')
def env():
    with tempfile.TemporaryDirectory(prefix='prod_prop_') as d:
        settings = Settings(database_path=Path(d) / 't.sqlite3', media_dir=Path(d) / 'media', demo_mode=True)
        app = create_app(settings)
        with TestClient(app, raise_server_exceptions=False) as client:
            conn = db.connect(settings.database_path)
            with db.transaction(conn):
                users_api.create_user(conn, name='S', email='seller@example.com',
                                      password_hash=hash_password(PASSWORD), role='seller')
            conn.close()
            token = client.post('/api/auth/login', json={'email': 'seller@example.com', 'password': PASSWORD}).json()['token']
            yield client, {'Authorization': f'Bearer {token}'}


def _total(client, headers) -> int:
    return client.get('/api/staff/products', headers=headers).json()['total']


@hsettings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
@given(name=names, description=descriptions, price=prices, stock=counts, threshold=st.one_of(st.none(), counts))
def test_create_accepts_iff_all_fields_in_range(env, name, description, price, stock, threshold):
    client, headers = env
    body = {'name': name, 'description': description, 'categoryId': 1, 'priceSen': price, 'stock': stock}
    if threshold is not None:
        body['lowStockThreshold'] = threshold
    invalid = set()
    if _bad_name(name):
        invalid.add('name')
    if len(description) > 2000:
        invalid.add('description')
    if _bad_price(price):
        invalid.add('priceSen')
    if _bad_count(stock):
        invalid.add('stock')
    if threshold is not None and _bad_count(threshold):
        invalid.add('lowStockThreshold')

    before = _total(client, headers)
    r = client.post('/api/staff/products', json=body, headers=headers)
    if not invalid:
        assert r.status_code == 201
        got = client.get(f"/api/staff/products/{r.json()['id']}", headers=headers).json()
        assert got['name'] == name.strip() and got['description'] == description
        assert got['priceSen'] == price and got['stock']['quantity'] == stock
        assert _total(client, headers) == before + 1
    else:
        assert r.status_code == 422
        reported = {d['field'] for d in r.json()['error']['details']}
        assert invalid <= reported
        assert _total(client, headers) == before


@hsettings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
@given(name=names, description=descriptions, price=prices, threshold=st.one_of(st.none(), counts))
def test_update_accepts_iff_all_fields_in_range(env, name, description, price, threshold):
    client, headers = env
    created = client.post('/api/staff/products', headers=headers, json={
        'name': 'Original', 'description': 'orig', 'categoryId': 1, 'priceSen': 1234, 'stock': 3})
    assert created.status_code == 201
    pid = created.json()['id']
    original = client.get(f'/api/staff/products/{pid}', headers=headers).json()

    body = {'name': name, 'description': description, 'categoryId': 2, 'priceSen': price}
    if threshold is not None:
        body['lowStockThreshold'] = threshold
    invalid = set()
    if _bad_name(name):
        invalid.add('name')
    if len(description) > 2000:
        invalid.add('description')
    if _bad_price(price):
        invalid.add('priceSen')
    if threshold is not None and _bad_count(threshold):
        invalid.add('lowStockThreshold')

    r = client.put(f'/api/staff/products/{pid}', json=body, headers=headers)
    after = client.get(f'/api/staff/products/{pid}', headers=headers).json()
    if not invalid:
        assert r.status_code == 200
        assert after['name'] == name.strip() and after['description'] == description and after['priceSen'] == price
    else:
        assert r.status_code == 422
        assert invalid <= {d['field'] for d in r.json()['error']['details']}
        assert after == original
