"""Additional inventory endpoint cases (Req 21.2, 21.3, 21.5, 21.7, 31.1); complements test_staff_inventory.py."""
from __future__ import annotations

import pytest

from app import db
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])
BASE = '/api/staff/inventory'


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


def _notifications(settings, pid):
    conn = db.connect(settings.database_path)
    n = conn.execute("SELECT COUNT(*) FROM notifications WHERE type = 'low_stock' AND related_id = ?", (pid,)).fetchone()[0]
    conn.close()
    return n


def test_customer_forbidden_and_anonymous_unauthorized_on_every_endpoint(client, staff, settings):
    pid = _product(client, staff)
    cust = _login(client, settings, 'customer')
    calls = [
        ('get', f'{BASE}/{pid}', None),
        ('post', f'{BASE}/{pid}/adjustments', {'delta': 1, 'reason': 'x'}),
        ('get', f'{BASE}/{pid}/adjustments', None),
        ('put', f'{BASE}/{pid}/threshold', {'lowStockThreshold': 1}),
    ]
    for method, url, body in calls:
        kwargs = {'json': body} if body is not None else {}
        assert getattr(client, method)(url, headers=cust, **kwargs).status_code == 403, (method, url)
        assert getattr(client, method)(url, **kwargs).status_code == 401, (method, url)
    # Forbidden calls changed nothing.
    assert client.get(f'{BASE}/{pid}', headers=staff).json()['quantity'] == 10
    assert client.get(f'{BASE}/{pid}/adjustments', headers=staff).json()['items'] == []


def test_adjustment_increase_response_and_history_entry(client, staff):
    pid = _product(client, staff, stock=5)
    r = client.post(f'{BASE}/{pid}/adjustments', headers=staff, json={'delta': 7, 'reason': 'restock'})
    assert r.status_code == 201
    assert r.json()['quantity'] == 12 and r.json()['lowStock'] is False
    item = client.get(f'{BASE}/{pid}/adjustments', headers=staff).json()['items'][0]
    assert item['delta'] == 7 and item['reason'] == 'restock'
    assert item['productId'] == pid and item['actorUserId'] and item['createdAt']


def test_increase_does_not_notify_but_decrease_to_low_does(client, staff, settings):
    pid = _product(client, staff, stock=5, threshold=3)
    client.post(f'{BASE}/{pid}/adjustments', headers=staff, json={'delta': 2, 'reason': 'in'})
    assert _notifications(settings, pid) == 0
    client.post(f'{BASE}/{pid}/adjustments', headers=staff, json={'delta': -4, 'reason': 'out'})
    assert _notifications(settings, pid) == 1


def test_low_stock_boundary_is_inclusive_and_threshold_zero_allowed(client, staff):
    pid = _product(client, staff, stock=5, threshold=3)
    r = client.post(f'{BASE}/{pid}/adjustments', headers=staff, json={'delta': -2, 'reason': 'x'})
    assert r.json()['quantity'] == 3 and r.json()['lowStock'] is True
    r = client.post(f'{BASE}/{pid}/adjustments', headers=staff, json={'delta': 1, 'reason': 'x'})
    assert r.json()['quantity'] == 4 and r.json()['lowStock'] is False
    r = client.put(f'{BASE}/{pid}/threshold', headers=staff, json={'lowStockThreshold': 0})
    assert r.status_code == 200 and r.json()['lowStockThreshold'] == 0 and r.json()['lowStock'] is False


def test_adjusting_down_to_exactly_zero_succeeds(client, staff):
    pid = _product(client, staff, stock=2)
    r = client.post(f'{BASE}/{pid}/adjustments', headers=staff, json={'delta': -2, 'reason': 'all gone'})
    assert r.status_code == 201 and r.json()['quantity'] == 0 and r.json()['lowStock'] is True


def test_list_reports_low_count_and_low_only_filters(client, staff):
    low = _product(client, staff, name='Aaa', stock=1, threshold=3)
    ok = _product(client, staff, name='Bbb', stock=50, threshold=3)
    body = client.get(BASE, headers=staff).json()
    ids = [i['productId'] for i in body['items']]
    assert low in ids and ok in ids and body['lowStockCount'] == 1
    only = client.get(BASE, params={'low_only': 'true'}, headers=staff).json()
    assert [i['productId'] for i in only['items']] == [low] and only['lowStockCount'] == 1


def test_unknown_product_is_404_for_adjust_history_and_threshold(client, staff):
    assert client.post(f'{BASE}/nope/adjustments', headers=staff, json={'delta': 1, 'reason': 'x'}).status_code == 404
    assert client.get(f'{BASE}/nope/adjustments', headers=staff).status_code == 404
    assert client.put(f'{BASE}/nope/threshold', headers=staff, json={'lowStockThreshold': 1}).status_code == 404


def test_unknown_field_rejected_and_stock_unchanged(client, staff):
    pid = _product(client, staff)
    r = client.post(f'{BASE}/{pid}/adjustments', headers=staff, json={'delta': 1, 'reason': 'x', 'extra': 1})
    assert r.status_code == 422
    r = client.put(f'{BASE}/{pid}/threshold', headers=staff, json={'lowStockThreshold': 1, 'extra': 1})
    assert r.status_code == 422
    inv = client.get(f'{BASE}/{pid}', headers=staff).json()
    assert inv['quantity'] == 10 and inv['lowStockThreshold'] == 3


def test_threshold_failure_leaves_threshold_unchanged(client, staff):
    pid = _product(client, staff, threshold=3)
    r = client.put(f'{BASE}/{pid}/threshold', headers=staff, json={'lowStockThreshold': -5})
    assert r.status_code == 422
    assert 'lowStockThreshold' in {d['field'] for d in r.json()['error']['details']}
    assert client.get(f'{BASE}/{pid}', headers=staff).json()['lowStockThreshold'] == 3
