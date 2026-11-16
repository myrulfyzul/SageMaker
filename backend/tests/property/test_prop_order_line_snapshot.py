"""Property 51: Order line snapshot.

**Validates: Requirements 14.7**
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
from app.modules.orders import api as orders_api

PASSWORD = ''.join(['Secret', '123'])
DELIVERY = {'name': 'Aisha Rahman', 'phone': '0123456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bunga, Taman Indah', 'postcode': '50450', 'state': 'Selangor'}
_counter = itertools.count()
PROFILE = dict(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))

price_st = st.integers(min_value=100, max_value=1_000_000)
name_st = st.text(alphabet=st.characters(whitelist_categories=('L', 'N'), max_codepoint=0x24F),
                  min_size=1, max_size=40)
qty_st = st.integers(min_value=1, max_value=5)
deactivate_st = st.booleans()


@pytest.fixture(scope='module')
def env():
    d = Path(tempfile.mkdtemp(prefix='snapshot_prop_'))
    settings = Settings(database_path=d / 't.sqlite3', media_dir=d / 'media', demo_mode=True)
    cm = TestClient(create_app(settings))
    client = cm.__enter__()
    yield client, settings
    cm.__exit__(None, None, None)
    shutil.rmtree(d, ignore_errors=True)


def _read_order(settings, order_id):
    conn = db.connect(settings.database_path)
    try:
        return orders_api.get_order(conn, order_id)
    finally:
        conn.close()


@hsettings(**PROFILE)
@given(price=price_st, name=name_st, qty=qty_st, new_price=price_st, new_name=name_st, deactivate=deactivate_st)
def test_order_lines_keep_checkout_name_and_price(env, price, name, qty, new_price, new_name, deactivate):
    client, settings = env
    pid = f'p{next(_counter)}'
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                     "updated_at) VALUES (?, ?, '', 1, ?, 1, 'now', 'now')", (pid, name, price))
        conn.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                     "VALUES (?, ?, NULL, 100, 100)", (pid, pid))
    conn.close()

    email = f'u{next(_counter)}@example.com'
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    login = client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()
    h = {'Authorization': f"Bearer {login['token']}"}
    assert client.post('/api/cart/lines', headers=h, json={'productId': pid, 'quantity': qty}).status_code == 200
    res = client.post('/api/checkout', headers=h, json={'idempotencyKey': f'idem-key-{next(_counter):08d}',
                                                         'delivery': DELIVERY, 'method': 'cod'})
    assert res.status_code == 201, res.text
    order_id = res.json()['id']
    before = _read_order(settings, order_id)
    assert len(before['lines']) == 1
    assert before['lines'][0]['name'] == name
    assert before['lines'][0]['unitPriceSen'] == price

    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("UPDATE products SET name = ?, price_sen = ?, is_active = ? WHERE id = ?",
                     (new_name, new_price, 0 if deactivate else 1, pid))
    conn.close()

    after = _read_order(settings, order_id)
    assert [(l['name'], l['unitPriceSen'], l['quantity'], l['lineTotalSen']) for l in after['lines']] == \
           [(l['name'], l['unitPriceSen'], l['quantity'], l['lineTotalSen']) for l in before['lines']]
    assert after['lines'][0]['name'] == name
    assert after['lines'][0]['unitPriceSen'] == price
    assert after['subtotalSen'] == before['subtotalSen'] == price * qty
    assert after['totalSen'] == before['totalSen']
