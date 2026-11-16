"""Analytics dashboard and sales (Req 19.2, 19.3, 19.5, 19.6, 26.1-26.7)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from hypothesis import given, settings as hsettings, strategies as st

from app import db
from app.modules.analytics.service import aov
from app.modules.orders import api as orders_api
from app.modules.orders.schemas import NewOrder, NewOrderLine
from app.modules.users import api as users_api
from app.security import hash_password
from app.time_utils import today_local

PASSWORD = ''.join(['Secret', '123'])
TZ = 'Asia/Kuala_Lumpur'


def _login(client, settings, role):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        users_api.create_user(conn, name='U', email=f'{role}@example.com', password_hash=hash_password(PASSWORD),
                              role=role)
    conn.close()
    token = client.post('/api/auth/login', json={'email': f'{role}@example.com', 'password': PASSWORD}).json()['token']
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture()
def staff(client, settings):
    return _login(client, settings, 'seller')


@pytest.fixture()
def conn(client, settings):
    c = db.connect(settings.database_path)
    yield c
    c.close()


def _order(conn, key, lines, status=None, payment='paid'):
    """lines: [(product_id, name, qty)] at 1000 sen each; shipping 800."""
    with db.transaction(conn):
        order, _ = orders_api.create_order(conn, NewOrder(
            user_id=1, idempotency_key=key, customer_name='A B', email='a@x.com', phone='0123456789',
            delivery_address='1 Road', payment_method='card', payment_status=payment, shipping_fee_sen=800,
            lines=[NewOrderLine(product_id=p, variation_id=None, sku_key=p, name=n, unit_price_sen=1000, quantity=q)
                   for p, n, q in lines]))
        if status:
            orders_api.update_fields(conn, order['id'], status=status)
    return order


def _range():
    today = today_local(TZ)
    return {'start': (today - timedelta(days=1)).isoformat(), 'end': today.isoformat()}


def test_aov_rounds_half_up():
    assert aov(0, 0) == 0
    assert aov(5, 2) == 3 and aov(7, 3) == 2 and aov(4, 2) == 2


@given(rev=st.integers(0, 10**9), n=st.integers(1, 10**4))
@hsettings(max_examples=50)
def test_aov_is_nearest_integer(rev, n):
    assert abs(aov(rev, n) * n - rev) * 2 <= n


def test_staff_only(client, settings):
    assert client.get('/api/staff/analytics/dashboard').status_code == 401
    customer = _login(client, settings, 'customer')
    assert client.get('/api/staff/analytics/dashboard', headers=customer).status_code == 403
    assert client.get('/api/staff/analytics/sales', params=_range(), headers=customer).status_code == 403


def test_empty_dashboard(client, staff):
    body = client.get('/api/staff/analytics/dashboard', headers=staff).json()
    assert body['kpis']['totalRevenueSen'] == 0 and body['kpis']['aovSen'] == 0
    assert len(body['salesByMonth']) == 12 and all(m['revenueSen'] == 0 for m in body['salesByMonth'])
    assert set(body['ordersByStatus']) == {'placed', 'confirmed', 'preparing', 'shipped', 'delivered',
                                           'cancelled', 'payment_failed'}
    assert body['bestSellers'] == []


def test_dashboard_excludes_cancelled_and_failed(client, staff, conn):
    _order(conn, 'a', [('p1', 'Alpha', 2)])  # 2800
    _order(conn, 'b', [('p2', 'Beta', 1)])  # 1800
    _order(conn, 'c', [('p3', 'Gamma', 9)], status='cancelled')
    _order(conn, 'd', [('p3', 'Gamma', 9)], status='payment_failed', payment='failed')
    body = client.get('/api/staff/analytics/dashboard', headers=staff).json()
    k = body['kpis']
    assert k['totalRevenueSen'] == 4600 and k['orderCount'] == 2 and k['aovSen'] == 2300
    assert k['pendingOrders'] == 2
    assert body['ordersByStatus']['cancelled'] == 1 and body['ordersByStatus']['payment_failed'] == 1
    assert [b['productId'] for b in body['bestSellers']] == ['p1', 'p2']
    assert body['salesByMonth'][-1]['revenueSen'] == 4600


def test_sales_range(client, staff, conn):
    _order(conn, 'a', [('p1', 'Alpha', 2)])
    _order(conn, 'b', [('p2', 'Beta', 2)])
    _order(conn, 'c', [('p3', 'Gamma', 1)])
    body = client.get('/api/staff/analytics/sales', params=_range(), headers=staff).json()
    assert body['totalRevenueSen'] == 2800 * 2 + 1800 and body['orderCount'] == 3
    assert body['aovSen'] == (body['totalRevenueSen'] * 2 + 3) // 6
    assert sum(m['revenueSen'] for m in body['monthly']) == body['totalRevenueSen']
    assert [t['name'] for t in body['topProducts']] == ['Alpha', 'Beta', 'Gamma']  # tie Alpha/Beta by name
    assert [t['name'] for t in body['bottomProducts']] == ['Gamma', 'Alpha', 'Beta']


def test_sales_zero_months_and_empty(client, staff):
    today = today_local(TZ)
    start = (today - timedelta(days=95)).isoformat()
    body = client.get('/api/staff/analytics/sales', params={'start': start, 'end': today.isoformat()},
                      headers=staff).json()
    assert 4 <= len(body['monthly']) <= 5 and body['monthly'] == sorted(body['monthly'], key=lambda m: m['month'])
    assert body['totalRevenueSen'] == 0 and body['aovSen'] == 0 and body['topProducts'] == []


def test_sales_range_errors(client, staff):
    r = client.get('/api/staff/analytics/sales', params={'start': '2025-02-01', 'end': '2025-01-01'}, headers=staff)
    assert r.status_code == 422 and r.json()['error']['code'] == 'invalid_range'
    r = client.get('/api/staff/analytics/sales', params={'start': '2022-01-01', 'end': '2024-01-01'}, headers=staff)
    assert r.status_code == 422 and r.json()['error']['code'] == 'range_too_long'
    ok = client.get('/api/staff/analytics/sales', params={'start': '2022-01-01', 'end': '2023-12-31'}, headers=staff)
    assert ok.status_code == 200 and len(ok.json()['monthly']) == 24
