"""Property 15: Cart add/remove round trip.

**Validates: Requirements 11.8, 11.11**
"""
from __future__ import annotations

import itertools
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app

PASSWORD = ''.join(['Secret', '123'])
# (product id, variation id) SKUs; p1/p2 plain, p3#1 a variation. All have ample stock.
SKUS = (('p1', None), ('p2', None), ('p3', 1))
_counter = itertools.count()
PROFILE = dict(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))

sku_st = st.sampled_from(SKUS)
qty_st = st.integers(min_value=1, max_value=20)
cart_st = st.dictionaries(sku_st, qty_st, max_size=3)


@pytest.fixture(scope='module')
def env():
    d = Path(tempfile.mkdtemp(prefix='cart_prop_'))
    settings = Settings(database_path=d / 't.sqlite3', media_dir=d / 'media', demo_mode=True)
    cm = TestClient(create_app(settings))
    client = cm.__enter__()
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        for pid, price in (('p1', 1000), ('p2', 250), ('p3', 400)):
            conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                         "updated_at) VALUES (?, ?, '', 1, ?, 1, 'now', 'now')", (pid, f'Name {pid}', price))
        conn.execute("INSERT INTO product_variations (id, product_id, label, price_delta_sen, is_active) "
                     "VALUES (1, 'p3', 'Large', 100, 1)")
        for sku_key, pid, vid in (('p1', 'p1', None), ('p2', 'p2', None), ('p3#1', 'p3', 1)):
            conn.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                         "VALUES (?, ?, ?, 1000, 1000)", (sku_key, pid, vid))
    conn.close()
    yield client
    cm.__exit__(None, None, None)
    shutil.rmtree(d, ignore_errors=True)


def _new_user(client):
    email = f'u{next(_counter)}@example.com'
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    token = client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
    return {'Authorization': f'Bearer {token}'}


def _contents(client, h):
    body = client.get('/api/cart', headers=h).json()
    return body, {(ln['productId'], ln['variationId']): ln['quantity'] for ln in body['lines']}


def _seed_cart(client, h, cart):
    for (pid, vid), qty in cart.items():
        assert client.post('/api/cart/lines', headers=h,
                           json={'productId': pid, 'variationId': vid, 'quantity': qty}).status_code == 200


@hsettings(**PROFILE)
@given(cart=cart_st, sku=sku_st, qty=qty_st)
def test_add_then_delete_line_restores_cart(env, cart, sku, qty):
    h = _new_user(env)
    cart = {k: v for k, v in cart.items() if k != sku}  # new line, not an increment
    _seed_cart(env, h, cart)
    before, before_contents = _contents(env, h)

    added = env.post('/api/cart/lines', headers=h,
                     json={'productId': sku[0], 'variationId': sku[1], 'quantity': qty})
    assert added.status_code == 200
    line = next(ln for ln in added.json()['lines'] if (ln['productId'], ln['variationId']) == sku)
    assert line['quantity'] == qty

    removed = env.delete(f"/api/cart/lines/{line['id']}", headers=h)
    assert removed.status_code == 200
    after, after_contents = _contents(env, h)
    assert after_contents == before_contents
    assert (after['subtotalSen'], after['deliveryFeeSen'], after['grandTotalSen']) == \
        (before['subtotalSen'], before['deliveryFeeSen'], before['grandTotalSen'])


@hsettings(**PROFILE)
@given(cart=cart_st, sku=sku_st, qty=qty_st)
def test_set_quantity_zero_removes_line(env, cart, sku, qty):
    h = _new_user(env)
    cart = {k: v for k, v in cart.items() if k != sku}
    _seed_cart(env, h, cart)
    _, before_contents = _contents(env, h)

    assert env.post('/api/cart/lines', headers=h,
                    json={'productId': sku[0], 'variationId': sku[1], 'quantity': qty}).status_code == 200
    r = env.put('/api/cart/lines', headers=h, json={'productId': sku[0], 'variationId': sku[1], 'quantity': 0})
    assert r.status_code == 200
    assert _contents(env, h)[1] == before_contents
