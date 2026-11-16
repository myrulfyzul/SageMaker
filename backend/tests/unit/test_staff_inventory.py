"""Staff inventory endpoints (Req 21.1 to 21.7)."""
from __future__ import annotations

import pytest

from app import db
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])


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


def _product(client, staff, name='Tote', stock=10, threshold=3):
    r = client.post('/api/staff/products', headers=staff, json={
        'name': name, 'categoryId': 1, 'priceSen': 3000, 'stock': stock, 'lowStockThreshold': threshold})
    assert r.status_code == 201
    return r.json()['id']


def test_rbac(client, settings):
    assert client.get('/api/staff/inventory').status_code == 401
    cust = _login(client, settings, 'customer')
    assert client.get('/api/staff/inventory', headers=cust).status_code == 403


def test_adjust_history_threshold_and_low_flag(client, staff):
    pid = _product(client, staff)
    inv = client.get(f'/api/staff/inventory/{pid}', headers=staff).json()
    assert inv['quantity'] == 10 and inv['lowStock'] is False and inv['name'] == 'Tote'
    assert client.get(f'/api/staff/inventory/{pid}/adjustments', headers=staff).json()['items'] == []

    r = client.post(f'/api/staff/inventory/{pid}/adjustments', headers=staff, json={'delta': -8, 'reason': 'damaged'})
    assert r.status_code == 201 and r.json()['quantity'] == 2 and r.json()['lowStock'] is True
    client.post(f'/api/staff/inventory/{pid}/adjustments', headers=staff, json={'delta': 1, 'reason': 'found'})
    hist = client.get(f'/api/staff/inventory/{pid}/adjustments', headers=staff).json()['items']
    assert [h['delta'] for h in hist][:2] == [1, -8]

    assert client.get('/api/staff/inventory', params={'low_only': 'true'}, headers=staff).json()['items'][0]['productId'] == pid
    r = client.put(f'/api/staff/inventory/{pid}/threshold', headers=staff, json={'lowStockThreshold': 1})
    assert r.status_code == 200 and r.json()['lowStock'] is False
    assert client.get('/api/staff/inventory', params={'low_only': 'true'}, headers=staff).json()['items'] == []


def test_insufficient_and_invalid(client, staff):
    pid = _product(client, staff, stock=2)
    r = client.post(f'/api/staff/inventory/{pid}/adjustments', headers=staff, json={'delta': -3, 'reason': 'x'})
    assert r.status_code == 409 and r.json()['error']['code'] == 'insufficient_stock'
    for body, field in [({'delta': 0, 'reason': 'x'}, 'delta'), ({'delta': 1_000_000_000, 'reason': 'x'}, 'delta'),
                        ({'delta': 1.5, 'reason': 'x'}, 'delta'), ({'delta': 1, 'reason': ''}, 'reason'),
                        ({'delta': 1, 'reason': 'x' * 256}, 'reason'), ({'delta': 1}, 'reason')]:
        r = client.post(f'/api/staff/inventory/{pid}/adjustments', headers=staff, json=body)
        assert r.status_code == 422 and field in {d['field'] for d in r.json()['error']['details']}
    assert client.get(f'/api/staff/inventory/{pid}', headers=staff).json()['quantity'] == 2
    assert client.get(f'/api/staff/inventory/{pid}/adjustments', headers=staff).json()['items'] == []
    for v in (-1, 1_000_000_000, 'a'):
        assert client.put(f'/api/staff/inventory/{pid}/threshold', headers=staff,
                          json={'lowStockThreshold': v}).status_code == 422
    assert client.get('/api/staff/inventory/nope', headers=staff).status_code == 404


def test_decrease_to_low_creates_notification(client, staff, settings):
    pid = _product(client, staff, stock=5, threshold=3)
    client.post(f'/api/staff/inventory/{pid}/adjustments', headers=staff, json={'delta': -3, 'reason': 'sold offline'})
    conn = db.connect(settings.database_path)
    n = conn.execute("SELECT COUNT(*) FROM notifications WHERE type = 'low_stock' AND related_id = ?", (pid,)).fetchone()[0]
    conn.close()
    assert n == 1
