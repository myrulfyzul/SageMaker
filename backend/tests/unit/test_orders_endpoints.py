"""Customer orders, payment retry and staff order state machine (Req 13.11-13.12, 14.9-14.10, 15, 22)."""
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


def _stock(settings):
    return _q(settings, "SELECT quantity FROM stock_levels WHERE sku_key = 'p1'")


def _checkout(client, token, key='idem-key-0001', method='card', outcome='success', qty=2):
    client.post('/api/cart/lines', headers=_h(token), json={'productId': 'p1', 'quantity': qty})
    body = {'idempotencyKey': key, 'delivery': DELIVERY, 'method': method}
    if outcome:
        body['outcome'] = outcome
    r = client.post('/api/checkout', headers=_h(token), json=body)
    assert r.status_code == 201, r.text
    return r.json()['id']


def _status(client, staff, oid, status, **extra):
    return client.post(f'/api/staff/orders/{oid}/status', headers=_h(staff), json={'status': status, **extra})


def test_customer_list_and_detail_scoping(client, settings):
    _seed(settings, 20)
    a = _user(client, settings, 'a@example.com')
    b = _user(client, settings, 'b@example.com')
    assert client.get('/api/orders', headers=_h(a)).json()['items'] == []
    ids = [_checkout(client, a, key=f'idem-key-000{i}', qty=1) for i in range(3)]
    page = client.get('/api/orders?limit=2', headers=_h(a)).json()
    assert page['total'] == 3 and len(page['items']) == 2 and page['hasMore'] is True
    assert client.get('/api/orders?limit=51', headers=_h(a)).status_code == 422
    assert client.get('/api/orders', headers=_h(b)).json()['total'] == 0
    detail = client.get(f'/api/orders/{ids[0]}', headers=_h(a)).json()
    assert detail['history'][0]['status'] == 'placed' and detail['productionLabel'] is None
    assert detail['delivery']['postcode'] == '50450' and len(detail['payments']) == 1
    foreign = client.get(f'/api/orders/{ids[0]}', headers=_h(b))
    missing = client.get('/api/orders/SM-NOPE000000', headers=_h(b))
    assert foreign.status_code == missing.status_code == 404 and foreign.json() == missing.json()


def test_staff_list_filter_search_and_roles(client, settings):
    _seed(settings, 20)
    a = _user(client, settings, 'a@example.com')
    staff = _user(client, settings, 's@example.com', 'seller')
    oid = _checkout(client, a, outcome='success', qty=1)
    _checkout(client, a, key='idem-key-0002', outcome='failed', qty=1)
    assert client.get('/api/staff/orders', headers=_h(a)).status_code == 403
    assert client.get('/api/staff/orders').status_code == 401
    assert client.get('/api/staff/orders', headers=_h(staff)).json()['total'] == 2
    only = client.get('/api/staff/orders?status=payment_failed', headers=_h(staff)).json()
    assert only['total'] == 1 and only['items'][0]['status'] == 'payment_failed'
    bad = client.get('/api/staff/orders?status=bogus', headers=_h(staff))
    assert bad.status_code == 422 and bad.json()['error']['code'] == 'invalid_filter'
    found = client.get(f'/api/staff/orders?q={oid.lower()[3:8]}', headers=_h(staff)).json()
    assert [o['id'] for o in found['items']] == [oid]
    assert client.get('/api/staff/orders?q=aisha', headers=_h(staff)).json()['total'] == 2
    assert client.get('/api/staff/orders?q=%25', headers=_h(staff)).json()['total'] == 0
    assert client.get('/api/staff/orders?q=', headers=_h(staff)).status_code == 422
    assert client.get(f'/api/staff/orders/{oid}', headers=_h(staff)).json()['id'] == oid
    assert client.get('/api/staff/orders/SM-NOPE000000', headers=_h(staff)).status_code == 404


def test_state_machine_history_notifications_and_cancel_restore(client, settings):
    _seed(settings)
    a = _user(client, settings, 'a@example.com')
    staff = _user(client, settings, 's@example.com', 'admin')
    oid = _checkout(client, a)
    assert _stock(settings) == 3

    r = _status(client, staff, oid, 'shipped')
    assert r.status_code == 409 and r.json()['error']['code'] == 'invalid_transition'
    assert 'placed' in r.json()['error']['message'] and 'shipped' in r.json()['error']['message']
    assert _status(client, staff, oid, 'confirmed').json()['status'] == 'confirmed'
    assert _status(client, staff, oid, 'confirmed').status_code == 409
    assert _status(client, staff, oid, 'preparing').status_code == 200
    for extra in ({}, {'shipping_reference': 'ab'}, {'shipping_reference': 'x' * 81}):
        bad = _status(client, staff, oid, 'shipped', **extra)
        assert bad.status_code == 422, extra
    shipped = _status(client, staff, oid, 'shipped', shipping_reference='  JNT123456 ')
    assert shipped.json()['shippingReference'] == 'JNT123456'
    assert _status(client, staff, oid, 'cancelled', reason='changed mind').status_code == 409
    assert _stock(settings) == 3
    assert _q(settings, 'SELECT COUNT(*) FROM order_history WHERE order_id = ?', oid) == 4
    assert _q(settings, "SELECT COUNT(*) FROM notifications WHERE related_id = ? AND title = 'Order update'", oid) == 3
    assert _status(client, staff, oid, 'delivered').status_code == 200
    assert _status(client, staff, oid, 'cancelled', reason='too late').status_code == 409


def test_cancel_requires_reason_and_restores_stock_once(client, settings):
    _seed(settings)
    a = _user(client, settings, 'a@example.com')
    staff = _user(client, settings, 's@example.com', 'seller')
    oid = _checkout(client, a)
    assert _status(client, staff, oid, 'cancelled').status_code == 422
    assert _status(client, staff, oid, 'cancelled', reason='no').status_code == 422
    assert _stock(settings) == 3
    done = _status(client, staff, oid, 'cancelled', reason='customer asked')
    assert done.status_code == 200 and done.json()['cancelReason'] == 'customer asked'
    assert _stock(settings) == 5
    assert _status(client, staff, oid, 'cancelled', reason='again').status_code == 409
    assert _stock(settings) == 5
    assert _q(settings, 'SELECT COUNT(*) FROM stock_adjustments WHERE order_id = ?', oid) == 2


def test_legacy_packing_is_read_as_preparing(client, settings):
    _seed(settings)
    a = _user(client, settings, 'a@example.com')
    staff = _user(client, settings, 's@example.com', 'seller')
    oid = _checkout(client, a)
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("UPDATE orders SET status = 'packing' WHERE id = ?", (oid,))
    conn.close()
    assert client.get(f'/api/staff/orders?status=preparing', headers=_h(staff)).json()['total'] == 1
    assert _status(client, staff, oid, 'shipped', shipping_reference='REF-123').status_code == 200


def test_payment_retry_success_stock_shortage_and_rearmed_restore(client, settings):
    _seed(settings)
    a = _user(client, settings, 'a@example.com')
    b = _user(client, settings, 'b@example.com')
    staff = _user(client, settings, 's@example.com', 'seller')
    oid = _checkout(client, a, outcome='failed')
    assert _stock(settings) == 5
    url = f'/api/orders/{oid}/payments'

    assert client.post(url, headers=_h(b), json={'method': 'card', 'outcome': 'success'}).status_code == 404
    assert client.post(url, headers=_h(a), json={'method': 'card'}).status_code == 422
    assert client.post(url, headers=_h(a), json={'method': 'card', 'outcome': 'success',
                                                  'card_number': '4111'}).status_code == 422

    again = client.post(url, headers=_h(a), json={'method': 'card', 'outcome': 'failed'})
    assert again.status_code == 200 and again.json()['status'] == 'payment_failed'
    assert len(again.json()['payments']) == 2

    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute('UPDATE stock_levels SET quantity = 1')
    conn.close()
    short = client.post(url, headers=_h(a), json={'method': 'card', 'outcome': 'success'})
    assert short.status_code == 409 and short.json()['error']['code'] == 'insufficient_stock'
    assert short.json()['error']['details'][0]['available'] == 1
    assert _stock(settings) == 1
    assert _q(settings, 'SELECT status FROM orders WHERE id = ?', oid) == 'payment_failed'
    assert _q(settings, 'SELECT COUNT(*) FROM payments WHERE order_id = ?', oid) == 2

    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute('UPDATE stock_levels SET quantity = 5')
    conn.close()
    ok = client.post(url, headers=_h(a), json={'method': 'card', 'outcome': 'success'})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body['status'] == 'placed' and body['paymentStatus'] == 'paid' and len(body['payments']) == 3
    assert _stock(settings) == 3
    assert client.post(url, headers=_h(a), json={'method': 'card', 'outcome': 'success'}).status_code == 409
    # stock restoration works again after the retry re-reserved stock
    assert _status(client, staff, oid, 'cancelled', reason='refund asked').status_code == 200
    assert _stock(settings) == 5


def test_confirming_creates_production_jobs_without_changing_fulfilment_status(client, settings):
    _seed(settings, 5)
    cust = _user(client, settings, 'prod@example.com')
    staff = _user(client, settings, 'prodstaff@example.com', 'seller')
    short = _checkout(client, cust, key='idem-key-prod1', qty=3)  # 5 - 3 = 2 left, below the 3 ordered
    assert client.get(f'/api/orders/{short}', headers=_h(cust)).json()['productionLabel'] is None
    r = _status(client, staff, short, 'confirmed')
    assert r.status_code == 200 and r.json()['status'] == 'confirmed'
    assert _q(settings, 'SELECT COUNT(*) FROM production_jobs WHERE order_id = ?', short) == 1
    detail = client.get(f'/api/orders/{short}', headers=_h(cust)).json()
    assert detail['productionLabel'] == 'order_confirmed' and detail['status'] == 'confirmed'

    plain = _checkout(client, cust, key='idem-key-prod2', qty=1)  # 2 - 1 = 1 left, covers the line
    _status(client, staff, plain, 'confirmed')
    assert _q(settings, 'SELECT COUNT(*) FROM production_jobs WHERE order_id = ?', plain) == 0
    assert client.get(f'/api/orders/{plain}', headers=_h(cust)).json()['productionLabel'] is None


def test_confirming_made_to_order_line_creates_job(client, settings):
    _seed(settings, 20)
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("UPDATE products SET made_to_order = 1 WHERE id = 'p1'")
    conn.close()
    cust = _user(client, settings, 'mto@example.com')
    staff = _user(client, settings, 'mtostaff@example.com', 'seller')
    oid = _checkout(client, cust, key='idem-key-mto01', qty=1)
    _status(client, staff, oid, 'confirmed')
    assert _q(settings, 'SELECT COUNT(*) FROM production_jobs WHERE order_id = ?', oid) == 1
