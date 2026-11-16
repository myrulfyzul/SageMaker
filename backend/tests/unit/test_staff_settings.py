"""Staff settings endpoints and default threshold on product creation (Req 6.4, 20.1)."""
from __future__ import annotations

import pytest

from app import db
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])
URL = '/api/staff/settings'


def _login(client, settings, role):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        users_api.create_user(conn, name='U', email=f'{role}@example.com', password_hash=hash_password(PASSWORD), role=role)
    conn.close()
    token = client.post('/api/auth/login', json={'email': f'{role}@example.com', 'password': PASSWORD}).json()['token']
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture()
def staff(client, settings):
    return _login(client, settings, 'seller')


def test_rbac(client, settings):
    assert client.get(URL).status_code == 401
    cust = _login(client, settings, 'customer')
    assert client.get(URL, headers=cust).status_code == 403
    assert client.put(URL, headers=cust, json={'defaultLowStockThreshold': 1}).status_code == 403


def test_default_get_put_and_validation(client, staff):
    assert client.get(URL, headers=staff).json() == {'defaultLowStockThreshold': 5}
    r = client.put(URL, headers=staff, json={'defaultLowStockThreshold': 12})
    assert r.status_code == 200 and r.json() == {'defaultLowStockThreshold': 12}
    assert client.get(URL, headers=staff).json()['defaultLowStockThreshold'] == 12
    for ok in (0, 999_999_999):
        assert client.put(URL, headers=staff, json={'defaultLowStockThreshold': ok}).status_code == 200
    for bad in (-1, 1_000_000_000, 'a', 1.5, True):
        assert client.put(URL, headers=staff, json={'defaultLowStockThreshold': bad}).status_code == 422
    assert client.put(URL, headers=staff, json={}).status_code == 422
    assert client.get(URL, headers=staff).json()['defaultLowStockThreshold'] == 999_999_999


def test_new_product_uses_configured_default(client, staff):
    client.put(URL, headers=staff, json={'defaultLowStockThreshold': 9})
    pid = client.post('/api/staff/products', headers=staff,
                      json={'name': 'Tote', 'categoryId': 1, 'priceSen': 3000, 'stock': 20}).json()['id']
    assert client.get(f'/api/staff/inventory/{pid}', headers=staff).json()['lowStockThreshold'] == 9
    pid2 = client.post('/api/staff/products', headers=staff,
                       json={'name': 'Bag', 'categoryId': 1, 'priceSen': 3000, 'stock': 20,
                             'lowStockThreshold': 2}).json()['id']
    assert client.get(f'/api/staff/inventory/{pid2}', headers=staff).json()['lowStockThreshold'] == 2
