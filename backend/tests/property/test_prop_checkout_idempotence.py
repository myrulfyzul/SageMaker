"""Property 20: Checkout idempotence.

**Validates: Requirements 12.9, 14.6**
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
DELIVERY = {'name': 'Aisha Rahman', 'phone': '0123456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bunga, Taman Indah', 'postcode': '50450', 'state': 'Selangor'}
_counter = itertools.count()
PROFILE = dict(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))

qty_st = st.integers(min_value=1, max_value=5)
repeats_st = st.integers(min_value=1, max_value=4)
method_outcome_st = st.sampled_from([('card', 'success'), ('fpx', 'failed'), ('ewallet', 'cancelled'),
                                     ('cod', None)])


@pytest.fixture(scope='module')
def env():
    d = Path(tempfile.mkdtemp(prefix='checkout_prop_'))
    settings = Settings(database_path=d / 't.sqlite3', media_dir=d / 'media', demo_mode=True)
    cm = TestClient(create_app(settings))
    client = cm.__enter__()
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                     "updated_at) VALUES ('p1', 'Bag', '', 1, 1000, 1, 'now', 'now')")
        conn.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                     "VALUES ('p1', 'p1', NULL, 100000, 100000)")
    conn.close()
    yield client, settings
    cm.__exit__(None, None, None)
    shutil.rmtree(d, ignore_errors=True)


def _snapshot(settings):
    conn = db.connect(settings.database_path)
    try:
        stock = conn.execute("SELECT quantity FROM stock_levels WHERE sku_key = 'p1'").fetchone()[0]
        adjustments = conn.execute("SELECT COUNT(*) FROM stock_adjustments").fetchone()[0]
        return stock, adjustments
    finally:
        conn.close()


def _order_count(settings, user_prefix):
    conn = db.connect(settings.database_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM orders WHERE checkout_id LIKE ?",
                            (f'{user_prefix}:%',)).fetchone()[0]
    finally:
        conn.close()


@hsettings(**PROFILE)
@given(qty=qty_st, repeats=repeats_st, mo=method_outcome_st)
def test_repeated_checkout_creates_one_order_and_no_extra_stock_effects(env, qty, repeats, mo):
    client, settings = env
    email = f'u{next(_counter)}@example.com'
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    login = client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()
    h = {'Authorization': f"Bearer {login['token']}"}
    assert client.post('/api/cart/lines', headers=h, json={'productId': 'p1', 'quantity': qty}).status_code == 200

    method, outcome = mo
    body = {'idempotencyKey': f'idem-key-{next(_counter):08d}', 'delivery': DELIVERY, 'method': method}
    if outcome:
        body['outcome'] = outcome

    first = client.post('/api/checkout', headers=h, json=body)
    assert first.status_code == 201, first.text
    after_first = _snapshot(settings)

    for _ in range(repeats):
        again = client.post('/api/checkout', headers=h, json=body)
        assert again.status_code == 200, again.text
        assert again.json()['id'] == first.json()['id']
        assert again.json()['totalSen'] == first.json()['totalSen']
        assert _snapshot(settings) == after_first

    user_id = next(iter(_user_ids(settings, email)))
    assert _order_count(settings, user_id) == 1


def _user_ids(settings, email):
    conn = db.connect(settings.database_path)
    try:
        return [str(r[0]) for r in conn.execute("SELECT id FROM users WHERE email = ?", (email,))]
    finally:
        conn.close()
