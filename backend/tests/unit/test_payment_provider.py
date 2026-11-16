"""Malaysian payment providers: validated per method, stored on the order and the payment record."""
from __future__ import annotations

from app import db

PASSWORD = ''.join(['Secret', '123'])
DELIVERY = {'name': 'Aisha Rahman', 'phone': '0123456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bunga, Taman Indah', 'postcode': '50450', 'state': 'Selangor'}


def _h(token):
    return {'Authorization': f'Bearer {token}'}


def _customer(client, email='p@example.com'):
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    return client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']


def _stock(settings, qty=5):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                     "updated_at) VALUES ('p1', 'Bag', '', 1, 1000, 1, 'now', 'now')")
        conn.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                     "VALUES ('p1', 'p1', NULL, ?, ?)", (qty, qty))
    conn.close()


def _checkout(client, token, key, method, outcome, provider=None):
    client.post('/api/cart/lines', headers=_h(token), json={'productId': 'p1', 'quantity': 1})
    body = {'idempotencyKey': key, 'delivery': DELIVERY, 'method': method, 'outcome': outcome}
    if provider is not None:
        body['provider'] = provider
    return client.post('/api/checkout', headers=_h(token), json=body)


def test_fpx_bank_is_stored_on_order_and_payment(client, settings):
    _stock(settings)
    t = _customer(client)
    r = _checkout(client, t, 'idem-fpx-00001', 'fpx', 'success', 'maybank2u')
    assert r.status_code == 201, r.text
    order = r.json()
    assert order['paymentProvider'] == 'maybank2u'
    assert order['payments'][0]['provider'] == 'maybank2u'
    detail = client.get(f"/api/orders/{order['id']}", headers=_h(t)).json()
    assert detail['paymentProvider'] == 'maybank2u'


def test_wrong_provider_for_method_is_rejected_without_an_order(client, settings):
    _stock(settings)
    t = _customer(client)
    for method, provider in (('fpx', 'tng'), ('ewallet', 'maybank2u'), ('card', 'maybank2u'), ('fpx', 'nope')):
        r = _checkout(client, t, f'idem-bad-{method}-{provider}', method, 'success', provider)
        assert r.status_code == 422, (method, provider, r.text)
        assert r.json()['error']['details'][0]['field'] == 'provider'
    assert client.get('/api/orders', headers=_h(t)).json()['total'] == 0


def test_provider_is_optional_and_retry_records_the_new_one(client, settings):
    _stock(settings)
    t = _customer(client)
    r = _checkout(client, t, 'idem-retry-0001', 'ewallet', 'failed', 'tng')
    order_id = r.json()['id']
    assert r.json()['status'] == 'payment_failed'
    retry = client.post(f'/api/orders/{order_id}/payments', headers=_h(t),
                        json={'method': 'ewallet', 'outcome': 'success', 'provider': 'duitnow'})
    assert retry.status_code == 200, retry.text
    assert retry.json()['paymentProvider'] == 'duitnow'
    assert [p['provider'] for p in retry.json()['payments']] == ['tng', 'duitnow']
    plain = _checkout(client, t, 'idem-plain-0001', 'card', 'success')
    assert plain.status_code == 201 and plain.json()['paymentProvider'] is None
