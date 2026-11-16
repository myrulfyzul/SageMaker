"""Payments: record(), GET /api/orders/{id}/payments, demo-mode gate, no card data (Req 13, 33.7)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings as hsettings, strategies as st
from pydantic import ValidationError

from app import db
from app.config import Settings
from app.main import create_app
from app.modules.orders import api as orders
from app.modules.orders.schemas import NewOrder, NewOrderLine
from app.modules.payments import api as payments
from app.modules.payments.schemas import PaymentRequest

PASSWORD = ''.join(['Secret', '123'])


def _h(token):
    return {'Authorization': f'Bearer {token}'}


def _user(client, settings, email, role='customer'):
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    if role != 'customer':
        conn = db.connect(settings.database_path)
        with db.transaction(conn):
            conn.execute('UPDATE users SET role = ? WHERE email = ?', (role, email))
        conn.close()
    token = client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
    return token


def _user_id(settings, email):
    conn = db.connect(settings.database_path)
    uid = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()[0]
    conn.close()
    return uid


def _order(settings, user_id, key='k1'):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        order, _ = orders.create_order(conn, NewOrder(
            user_id=user_id, idempotency_key=key, customer_name='A B', email='a@x.com', phone='0123456789',
            delivery_address='1 Road', payment_method='card', payment_status='paid', shipping_fee_sen=800,
            lines=[NewOrderLine(product_id='p1', variation_id=None, sku_key='p1', name='T', unit_price_sen=1000,
                                quantity=1)]))
        payments.record(conn, order['id'], 'card', 'success', order['totalSen'])
    conn.close()
    return order['id']


def test_owner_and_staff_see_payments_others_get_identical_404(client, settings):
    a = _user(client, settings, 'a@example.com')
    b = _user(client, settings, 'b@example.com')
    staff = _user(client, settings, 's@example.com', role='seller')
    oid = _order(settings, _user_id(settings, 'a@example.com'))

    for tok in (a, staff):
        r = client.get(f'/api/orders/{oid}/payments', headers=_h(tok))
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1 and body[0]['isDemo'] is True and body[0]['amountSen'] == 1800
        assert body[0]['method'] == 'card' and body[0]['outcome'] == 'success'

    foreign = client.get(f'/api/orders/{oid}/payments', headers=_h(b))
    missing = client.get('/api/orders/SM-NOPE000000/payments', headers=_h(b))
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert client.get('/api/orders/SM-NOPE000000/payments', headers=_h(staff)).status_code == 404
    assert client.get(f'/api/orders/{oid}/payments').status_code == 401


def test_non_demo_mode_returns_503_and_records_nothing(settings):
    off = Settings(database_path=settings.database_path, media_dir=settings.media_dir, demo_mode=False)
    with TestClient(create_app(off), raise_server_exceptions=False) as c:
        r = c.get('/api/orders/SM-ABCDEFGHIJ/payments')
        assert r.status_code == 503 and r.json()['error']['code'] == 'payments_not_configured'
        conn = db.connect(settings.database_path)
        assert conn.execute('SELECT COUNT(*) FROM payments').fetchone()[0] == 0
        conn.close()


def test_request_schema_rejects_card_data():
    assert PaymentRequest(method='card', outcome='success').method == 'card'
    with pytest.raises(ValidationError):
        PaymentRequest(method='card', outcome='success', card_number='4111111111111111')


@given(method=st.sampled_from(['card', 'fpx', 'ewallet', 'cod']), amount=st.integers(min_value=-5, max_value=10_000))
@hsettings(max_examples=40, deadline=None)
def test_record_property(method, amount):
    import sqlite3
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE payments (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, method TEXT, "
                 "outcome TEXT, amount_sen INTEGER CHECK (amount_sen > 0), is_demo INTEGER DEFAULT 1, "
                 "created_at TEXT)")
    outcome = 'pending_cod' if method == 'cod' else 'success'
    if amount <= 0:
        with pytest.raises(ValueError):
            payments.record(conn, 'SM-X', method, outcome, amount)
    else:
        rec = payments.record(conn, 'SM-X', method, outcome, amount)
        assert rec['isDemo'] is True and rec['amountSen'] == amount
    with pytest.raises(ValueError):
        payments.record(conn, 'SM-X', 'bitcoin', 'success', 100)
    with pytest.raises(ValueError):
        payments.record(conn, 'SM-X', 'cod', 'success', 100)
