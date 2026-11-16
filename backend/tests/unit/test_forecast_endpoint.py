"""GET /api/staff/forecast/{product_id} (Req 27.1, 27.6, 27.7, 27.10, 27.11)."""
from __future__ import annotations

import pytest

from app import db
from app.modules.forecasting import service as forecast_service
from app.modules.orders import api as orders_api
from app.modules.orders.schemas import NewOrder, NewOrderLine
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])


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
def product_id(client, staff):
    body = {'name': 'Tote', 'description': 'Nice', 'categoryId': 1, 'priceSen': 3000, 'stock': 10}
    return client.post('/api/staff/products', json=body, headers=staff).json()['id']


def _sell(settings, product_id, qty, key='k1'):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        orders_api.create_order(conn, NewOrder(
            user_id=1, idempotency_key=key, customer_name='A B', email='a@x.com', phone='0123456789',
            delivery_address='1 Road', payment_method='card', payment_status='paid', shipping_fee_sen=800,
            lines=[NewOrderLine(product_id=product_id, variation_id=None, sku_key=product_id, name='Tote',
                                unit_price_sen=3000, quantity=qty)]))
    conn.close()


def test_staff_only(client, settings, product_id):
    url = f'/api/staff/forecast/{product_id}'
    assert client.get(url).status_code == 401
    assert client.get(url, headers=_login(client, settings, 'customer')).status_code == 403


def test_unknown_product_404(client, staff):
    assert client.get('/api/staff/forecast/nope', headers=staff).status_code == 404


def test_no_history_422(client, staff, product_id):
    r = client.get(f'/api/staff/forecast/{product_id}', headers=staff)
    assert r.status_code == 422 and r.json()['error']['code'] == 'forecast_no_history'


def test_forecast_shape(client, settings, staff, product_id):
    _sell(settings, product_id, 3)
    r = client.get(f'/api/staff/forecast/{product_id}', headers=staff)
    assert r.status_code == 200
    body = r.json()
    assert body['productId'] == product_id and body['synthetic'] is False
    assert len(body['history']) == 1 and body['history'][0]['units'] == 3
    assert len(body['baseline']['forecast']) == 3 and body['candidate'] is None
    assert body['evaluation'] == {'available': False, 'reason': 'insufficient_history'}
    assert body['selectedModel'] == 'baseline'
    assert isinstance(body['replenish'], bool)


def test_core_failure_500_safe(client, settings, staff, product_id, monkeypatch):
    _sell(settings, product_id, 3)

    def boom(*a, **k):
        raise RuntimeError('secret /path/to/file')

    monkeypatch.setattr(forecast_service, 'forecast_series', boom)
    r = client.get(f'/api/staff/forecast/{product_id}', headers=staff)
    assert r.status_code == 500
    err = r.json()['error']
    assert err['code'] == 'forecast_failed' and 'secret' not in err['message']
