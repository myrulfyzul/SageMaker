"""POST /api/checkout: outcomes, idempotency, validation, stock, notifications (Req 12-14)."""
from __future__ import annotations

import dataclasses

import pytest

from app import db

PASSWORD = ''.join(['Secret', '123'])
DELIVERY = {'name': 'Aisha Rahman', 'phone': '0123456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bunga, Taman Indah', 'postcode': '50450', 'state': 'Selangor'}


def _h(token):
    return {'Authorization': f'Bearer {token}'}


def _customer(client, email='a@example.com'):
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    return client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']


def _seed(settings, stock=5):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                     "updated_at) VALUES ('p1', 'Bag', '', 1, 1000, 1, 'now', 'now')")
        conn.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                     "VALUES ('p1', 'p1', NULL, ?, ?)", (stock, stock))
    conn.close()


def _stock(settings):
    conn = db.connect(settings.database_path)
    try:
        return conn.execute("SELECT quantity FROM stock_levels WHERE sku_key = 'p1'").fetchone()[0]
    finally:
        conn.close()


def _body(key='idem-key-0001', method='card', outcome='success', **delivery):
    body = {'idempotencyKey': key, 'delivery': {**DELIVERY, **delivery}, 'method': method}
    if outcome:
        body['outcome'] = outcome
    return body


def _fill(client, t, qty=2):
    assert client.post('/api/cart/lines', headers=_h(t), json={'productId': 'p1', 'quantity': qty}).status_code == 200


@pytest.mark.parametrize('method,outcome,pay,status,stock', [
    ('card', 'success', 'paid', 'placed', 3),
    ('fpx', 'failed', 'failed', 'payment_failed', 5),
    ('ewallet', 'cancelled', 'cancelled', 'cancelled', 5),
    ('cod', None, 'pending_cod', 'placed', 3),
])
def test_outcome_mapping(client, settings, method, outcome, pay, status, stock):
    _seed(settings)
    t = _customer(client)
    _fill(client, t)
    r = client.post('/api/checkout', headers=_h(t), json=_body(method=method, outcome=outcome))
    assert r.status_code == 201, r.text
    order = r.json()
    assert (order['paymentStatus'], order['status']) == (pay, status)
    assert order['id'].startswith('SM-') and len(order['id']) == 13
    assert order['totalSen'] == 2800 and len(order['payments']) == 1 and order['payments'][0]['isDemo'] is True
    assert _stock(settings) == stock
    assert client.get('/api/cart', headers=_h(t)).json()['lines'] == []
    conn = db.connect(settings.database_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM notifications WHERE related_id = ?", (order['id'],)).fetchone()[0]
    finally:
        conn.close()
    assert count == 1  # customer only: no staff users exist in this fixture


def test_idempotent_repeat_returns_original_without_writes(client, settings):
    _seed(settings)
    t = _customer(client)
    _fill(client, t)
    first = client.post('/api/checkout', headers=_h(t), json=_body())
    _fill(client, t, 1)
    second = client.post('/api/checkout', headers=_h(t), json=_body())
    assert second.status_code == 200 and second.json()['id'] == first.json()['id']
    assert _stock(settings) == 3
    assert len(client.get('/api/cart', headers=_h(t)).json()['lines']) == 1


def test_validation_empty_cart_and_stock(client, settings):
    _seed(settings, stock=1)
    t = _customer(client)
    assert client.post('/api/checkout', headers=_h(t), json=_body()).status_code == 400
    _fill(client, t, 1)
    bad = client.post('/api/checkout', headers=_h(t), json=_body(postcode='123', state='Atlantis', name='A'))
    assert bad.status_code == 422
    assert {d['field'] for d in bad.json()['error']['details']} == {
        'delivery.postcode', 'delivery.state', 'delivery.name'}
    assert client.post('/api/checkout', headers=_h(t), json=_body(key='short')).status_code == 422
    # stock goes short after the item was added
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("UPDATE stock_levels SET quantity = 0")
    conn.close()
    r = client.post('/api/checkout', headers=_h(t), json=_body())
    assert r.status_code == 409 and r.json()['error']['details'][0]['productId'] == 'p1'
    assert _stock(settings) == 0


def test_auth_and_demo_mode(client, app, settings):
    assert client.post('/api/checkout', json=_body()).status_code == 401
    app.state.settings = dataclasses.replace(settings, demo_mode=False)
    t = _customer(client)
    assert client.post('/api/checkout', headers=_h(t), json=_body()).status_code == 503
