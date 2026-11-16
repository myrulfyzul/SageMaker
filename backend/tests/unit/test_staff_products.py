"""Staff product management: create, edit, activate, delete rule, image upload and RBAC (Req 20.1 to 20.10)."""
from __future__ import annotations

import pytest

from app import db
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])
PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 20


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


def _create(client, staff, **over):
    body = {'name': 'Tote', 'description': 'Nice', 'categoryId': 1, 'priceSen': 3000, 'stock': 10, **over}
    return client.post('/api/staff/products', json=body, headers=staff)


def test_create_get_list_and_search(client, staff):
    r = _create(client, staff, lowStockThreshold=4)
    assert r.status_code == 201
    p = r.json()
    assert p['priceSen'] == 3000 and p['isActive'] is True and p['stock']['quantity'] == 10
    assert client.get(f"/api/products/{p['id']}").status_code == 200
    assert client.get(f"/api/staff/products/{p['id']}", headers=staff).json()['id'] == p['id']
    lst = client.get('/api/staff/products', params={'q': 'tot'}, headers=staff).json()
    assert lst['total'] == 1


def test_create_with_variations_sums_stock(client, staff):
    r = _create(client, staff, stock=0, variations=[{'label': 'S', 'stock': 2}, {'label': 'L', 'priceDeltaSen': 500, 'stock': 3}])
    assert r.status_code == 201
    p = r.json()
    assert p['stock']['quantity'] == 5 and [v['stockQuantity'] for v in p['variations']] == [2, 3]
    assert _create(client, staff, stock=1, variations=[{'label': 'S'}]).status_code == 422


@pytest.mark.parametrize('over,fields', [
    ({'name': ''}, {'name'}), ({'name': 'x' * 201}, {'name'}), ({'priceSen': 0}, {'priceSen'}),
    ({'priceSen': 100_000_000}, {'priceSen'}), ({'stock': -1}, {'stock'}), ({'lowStockThreshold': -1}, {'lowStockThreshold'}),
    ({'description': 'x' * 2001}, {'description'}), ({'categoryId': 99}, {'categoryId'}),
    ({'artisanId': 5}, {'artisanId'}), ({'name': '', 'priceSen': 0}, {'name', 'priceSen'}),
])
def test_validation_rejects_each_invalid_field(client, staff, over, fields):
    r = _create(client, staff, **over)
    assert r.status_code == 422
    assert fields <= {d['field'] for d in r.json()['error']['details']}
    assert client.get('/api/staff/products', headers=staff).json()['total'] == 0


def test_update_deactivate_reactivate(client, staff):
    pid = _create(client, staff).json()['id']
    r = client.put(f'/api/staff/products/{pid}', json={'name': 'Bag', 'categoryId': 2, 'priceSen': 4000,
                                                       'lowStockThreshold': 50}, headers=staff)
    assert r.status_code == 200
    assert r.json()['name'] == 'Bag' and r.json()['priceSen'] == 4000 and r.json()['description'] == 'Nice'
    assert r.json()['stock']['status'] == 'low_stock'
    assert client.put(f'/api/staff/products/{pid}', json={'name': 'Bag', 'categoryId': 2, 'priceSen': 0},
                      headers=staff).status_code == 422

    assert client.patch(f'/api/staff/products/{pid}/active', json={'isActive': False}, headers=staff).json()['isActive'] is False
    assert client.get('/api/products').json()['total'] == 0
    assert client.get(f'/api/products/{pid}').status_code == 404
    client.patch(f'/api/staff/products/{pid}/active', json={'isActive': True}, headers=staff)
    assert client.get('/api/products').json()['total'] == 1
    assert client.put('/api/staff/products/nope', json={'name': 'a', 'categoryId': 1, 'priceSen': 1},
                      headers=staff).status_code == 404


def test_update_variations_deactivates_omitted(client, staff):
    p = _create(client, staff, stock=0, variations=[{'label': 'S', 'stock': 2}, {'label': 'L', 'stock': 3}]).json()
    s, large = p['variations']
    r = client.put(f"/api/staff/products/{p['id']}", headers=staff, json={
        'name': 'Tote', 'categoryId': 1, 'priceSen': 3000,
        'variations': [{'id': s['id'], 'label': 'Small'}, {'label': 'XL', 'stock': 1}]})
    assert r.status_code == 200
    by_label = {v['label']: v for v in r.json()['variations']}
    assert by_label['L']['isActive'] is False and by_label['Small']['stockQuantity'] == 2
    assert by_label['XL']['stockQuantity'] == 1
    bad = client.put(f"/api/staff/products/{p['id']}", headers=staff, json={
        'name': 'Tote', 'categoryId': 1, 'priceSen': 3000, 'variations': [{'id': 9999, 'label': 'x'}]})
    assert bad.status_code == 422


def test_delete_without_orders_and_with_orders(client, settings, staff):
    free = _create(client, staff).json()['id']
    used = _create(client, staff, name='Used').json()['id']
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        cols = [r['name'] for r in conn.execute('PRAGMA table_info(orders)') if r['notnull'] and r['dflt_value'] is None]
        values = {c: 'x' for c in cols}
        values['id'] = 'SM-1'
        conn.execute(f"INSERT INTO orders ({','.join(values)}) VALUES ({','.join('?' * len(values))})", list(values.values()))
        conn.execute("INSERT INTO order_lines (order_id, product_id, sku_key, name, unit_price_sen, quantity, line_total_sen) "
                     "VALUES ('SM-1', ?, ?, 'Used', 3000, 1, 3000)", (used, used))
    conn.close()

    assert client.delete(f'/api/staff/products/{free}', headers=staff).status_code == 204
    assert client.get(f'/api/staff/products/{free}', headers=staff).status_code == 404
    r = client.delete(f'/api/staff/products/{used}', headers=staff)
    assert r.status_code == 409 and r.json()['error']['code'] == 'product_in_orders'
    assert client.get(f'/api/staff/products/{used}', headers=staff).status_code == 200
    assert client.delete(f'/api/staff/products/{free}', headers=staff).status_code == 404


def test_image_upload_accept_and_reject(client, settings, staff):
    pid = _create(client, staff).json()['id']
    url = f'/api/staff/products/{pid}/images'
    ok = client.post(url, files={'file': ('client-name.png', PNG, 'image/png')}, headers=staff)
    assert ok.status_code == 201 and len(ok.json()['images']) == 1
    stored = ok.json()['images'][0]['url']
    assert stored.startswith('/media/') and 'client-name' not in stored
    for name, data in (('a.gif', PNG), ('a.png', b'<script>'), ('a.jpg', PNG)):
        bad = client.post(url, files={'file': (name, data, 'image/png')}, headers=staff)
        assert bad.status_code == 422
    big = client.post(url, files={'file': ('a.png', PNG + b'0' * (5 * 1024 * 1024), 'image/png')}, headers=staff)
    assert big.status_code == 422 and big.json()['error']['code'] == 'image_too_large'
    assert len(client.get(f'/api/staff/products/{pid}', headers=staff).json()['images']) == 1
    assert client.post('/api/staff/products/nope/images', files={'file': ('a.png', PNG, 'image/png')},
                       headers=staff).status_code == 404


def test_rbac(client, settings):
    endpoints = [('get', '/api/staff/products'), ('post', '/api/staff/products'), ('get', '/api/staff/products/x'),
                 ('put', '/api/staff/products/x'), ('delete', '/api/staff/products/x'),
                 ('patch', '/api/staff/products/x/active')]
    for method, url in endpoints:
        assert getattr(client, method)(url).status_code == 401
    client.post('/api/auth/register', json={'name': 'C', 'email': 'c@example.com', 'password': PASSWORD})
    token = client.post('/api/auth/login', json={'email': 'c@example.com', 'password': PASSWORD}).json()['token']
    cust = {'Authorization': f'Bearer {token}'}
    for method, url in endpoints:
        assert getattr(client, method)(url, headers=cust).status_code == 403
    assert client.post('/api/staff/products/x/images', headers=cust,
                       files={'file': ('a.png', PNG, 'image/png')}).status_code == 403
    admin = _login(client, settings, 'admin')
    assert client.get('/api/staff/products', headers=admin).status_code == 200
