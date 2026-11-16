"""Gap-filling commerce tests: cart, checkout, payments, orders, legacy smoke (Task 7.25).

Validates: Requirements 1.1, 11.6, 12.9, 13.3, 14.5, 15.1, 22.5, 31.1
"""
from __future__ import annotations

from app import db

PASSWORD = ''.join(['Secret', '123'])
DELIVERY = {'name': 'Aisha Rahman', 'phone': '0123456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bunga, Taman Indah', 'postcode': '50450', 'state': 'Selangor'}


def _h(token):
    return {'Authorization': f'Bearer {token}'}


def _user(client, settings, email, role='customer'):
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    if role != 'customer':
        conn = db.connect(settings.database_path)
        with db.transaction(conn):
            conn.execute('UPDATE users SET role = ? WHERE email = ?', (role, email))
        conn.close()
    return client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']


def _seed(settings, stock=5):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                     "updated_at) VALUES ('p1', 'Bag', '', 1, 1000, 1, 'now', 'now')")
        conn.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                     "VALUES ('p1', 'p1', NULL, ?, ?)", (stock, stock))
    conn.close()


def _q(settings, sql, *args):
    conn = db.connect(settings.database_path)
    try:
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()


def _checkout_body(key='idem-key-0001', method='card', outcome='success'):
    body = {'idempotencyKey': key, 'delivery': DELIVERY, 'method': method}
    if outcome:
        body['outcome'] = outcome
    return body


def _add(client, t, qty=2, pid='p1'):
    return client.post('/api/cart/lines', headers=_h(t), json={'productId': pid, 'quantity': qty})


def test_add_unknown_product_fails_and_cart_unchanged(client, settings):
    _seed(settings)
    t = _user(client, settings, 'a@example.com')
    r = _add(client, t, 1, pid='does-not-exist')
    assert r.status_code in (404, 409, 422)
    assert client.get('/api/cart', headers=_h(t)).json()['lines'] == []


def test_merge_into_empty_cart_succeeds_and_requires_auth(client, settings):
    _seed(settings)
    assert client.post('/api/cart/merge', json={'lines': []}).status_code == 401
    t = _user(client, settings, 'a@example.com')
    r = client.post('/api/cart/merge', headers=_h(t), json={'lines': [{'productId': 'p1', 'quantity': 3}]})
    assert r.status_code == 200
    body = r.json()
    assert body['notMerged'] == []
    assert [(x['productId'], x['quantity']) for x in body['cart']['lines']] == [('p1', 3)]


def test_checkout_rejects_unknown_method_and_outcome_without_side_effects(client, settings):
    _seed(settings)
    t = _user(client, settings, 'a@example.com')
    _add(client, t)
    assert client.post('/api/checkout', headers=_h(t), json=_checkout_body(method='bitcoin')).status_code == 422
    assert client.post('/api/checkout', headers=_h(t), json=_checkout_body(outcome='maybe')).status_code == 422
    assert _q(settings, 'SELECT COUNT(*) FROM orders') == 0
    assert _q(settings, "SELECT quantity FROM stock_levels WHERE sku_key = 'p1'") == 5
    assert len(client.get('/api/cart', headers=_h(t)).json()['lines']) == 1


def test_order_history_lists_newest_first_and_requires_auth(client, settings):
    _seed(settings, 20)
    assert client.get('/api/orders').status_code == 401
    t = _user(client, settings, 'a@example.com')
    ids = []
    for i in range(2):
        _add(client, t, 1)
        r = client.post('/api/checkout', headers=_h(t), json=_checkout_body(key=f'idem-key-100{i}'))
        assert r.status_code == 201
        ids.append(r.json()['id'])
    listed = client.get('/api/orders', headers=_h(t)).json()
    assert listed['total'] == 2 and {o['id'] for o in listed['items']} == set(ids)
    assert listed['hasMore'] is False


def test_status_update_rejects_customer_unknown_status_and_unknown_order(client, settings):
    _seed(settings)
    a = _user(client, settings, 'a@example.com')
    staff = _user(client, settings, 's@example.com', 'admin')
    _add(client, a)
    oid = client.post('/api/checkout', headers=_h(a), json=_checkout_body()).json()['id']
    url = f'/api/staff/orders/{oid}/status'
    assert client.post(url, json={'status': 'confirmed'}).status_code == 401
    assert client.post(url, headers=_h(a), json={'status': 'confirmed'}).status_code == 403
    assert client.post(url, headers=_h(staff), json={'status': 'teleported'}).status_code == 422
    assert client.post('/api/staff/orders/SM-NOPE000000/status', headers=_h(staff),
                       json={'status': 'confirmed'}).status_code == 404
    assert _q(settings, 'SELECT status FROM orders WHERE id = ?', oid) == 'placed'


def test_cod_order_payment_pending_and_retry_rejected(client, settings):
    _seed(settings)
    t = _user(client, settings, 'a@example.com')
    _add(client, t)
    order = client.post('/api/checkout', headers=_h(t), json=_checkout_body(method='cod', outcome=None)).json()
    assert order['paymentStatus'] == 'pending_cod' and order['status'] == 'placed'
    r = client.post(f"/api/orders/{order['id']}/payments", headers=_h(t),
                    json={'method': 'card', 'outcome': 'success'})
    assert r.status_code == 409


def test_legacy_smoke_products_order_and_client_price_rejected(client):
    items = client.get('/api/legacy/products').json()
    assert len(items) >= 1
    body = {'checkout_id': 'smoke-commerce-0001', 'customer_name': 'Demo Buyer', 'email': 'demo@example.com',
            'phone': '0123456789', 'delivery_address': '123 Sample Street, Sample City',
            'payment_method': 'demo_card', 'items': [{'product_id': 'fishing', 'quantity': 1}]}
    ok = client.post('/api/legacy/orders', json=body)
    assert ok.status_code == 201 and ok.json()['id'].startswith('DEMO-')
    assert ok.json()['items'][0]['unitPriceSen'] == 3500
    unknown = {**body, 'checkout_id': 'smoke-commerce-0002', 'items': [{'product_id': 'fake', 'quantity': 1}]}
    assert client.post('/api/legacy/orders', json=unknown).status_code == 400
    priced = {**body, 'checkout_id': 'smoke-commerce-0003',
              'items': [{'product_id': 'fishing', 'quantity': 1, 'price': 0}]}
    r = client.post('/api/legacy/orders', json=priced)
    assert r.status_code == 201 and r.json()['items'][0]['unitPriceSen'] == 3500  # client price ignored
