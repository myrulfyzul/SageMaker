"""Gap-filling catalogue/product CRUD endpoint tests (Req 9.1, 9.3, 9.14, 20.9, 20.10, 31.1)."""
from __future__ import annotations

import pytest

from app import db
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])
PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 20


def _staff(client, settings, role='seller'):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        users_api.create_user(conn, name='U', email=f'{role}@example.com', password_hash=hash_password(PASSWORD), role=role)
    conn.close()
    token = client.post('/api/auth/login', json={'email': f'{role}@example.com', 'password': PASSWORD}).json()['token']
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture()
def staff(client, settings):
    return _staff(client, settings)


@pytest.fixture()
def customer(client):
    client.post('/api/auth/register', json={'name': 'C', 'email': 'c@example.com', 'password': PASSWORD})
    token = client.post('/api/auth/login', json={'email': 'c@example.com', 'password': PASSWORD}).json()['token']
    return {'Authorization': f'Bearer {token}'}


def _create(client, staff, **over):
    body = {'name': 'Tote', 'description': 'Nice', 'categoryId': 1, 'priceSen': 3000, 'stock': 10, **over}
    r = client.post('/api/staff/products', json=body, headers=staff)
    assert r.status_code == 201, r.text
    return r.json()


def test_staff_list_includes_inactive_and_filters(client, staff):
    a = _create(client, staff, name='Alpha Tote', categoryId=1)
    b = _create(client, staff, name='Beta Toy', categoryId=3, description='wool')
    client.patch(f"/api/staff/products/{b['id']}/active", json={'isActive': False}, headers=staff)

    assert client.get('/api/staff/products', headers=staff).json()['total'] == 2
    only_inactive = client.get('/api/staff/products', params={'active': 'false'}, headers=staff).json()
    assert [i['id'] for i in only_inactive['items']] == [b['id']]
    only_active = client.get('/api/staff/products', params={'active': 'true'}, headers=staff).json()
    assert [i['id'] for i in only_active['items']] == [a['id']]
    by_cat = client.get('/api/staff/products', params={'category': 'toys'}, headers=staff).json()
    assert [i['id'] for i in by_cat['items']] == [b['id']]
    by_q = client.get('/api/staff/products', params={'q': 'WOOL'}, headers=staff).json()
    assert [i['id'] for i in by_q['items']] == [b['id']]
    assert client.get('/api/staff/products', params={'q': 'zzz'}, headers=staff).json()['total'] == 0
    page = client.get('/api/staff/products', params={'limit': 1, 'offset': 1}, headers=staff).json()
    assert len(page['items']) == 1 and page['total'] == 2


def test_staff_list_parameter_validation(client, staff):
    for params in ({'q': 'x' * 101}, {'limit': 0}, {'offset': -1}, {'active': 'maybe'}):
        r = client.get('/api/staff/products', params=params, headers=staff)
        assert r.status_code == 422 and r.json()['error']['code'] == 'validation_error'


def test_inactive_product_hidden_from_public_everywhere(client, staff, customer):
    p = _create(client, staff, name='Secret Tote')
    client.patch(f"/api/staff/products/{p['id']}/active", json={'isActive': False}, headers=staff)
    assert client.get('/api/products', params={'q': 'Secret'}).json()['total'] == 0
    assert client.get('/api/products', params={'category': 'tote-bags'}).json()['total'] == 0
    assert client.get(f"/api/products/{p['id']}").status_code == 404
    assert client.get(f"/api/products/{p['id']}", headers=customer).status_code == 404
    # staff can still see it
    assert client.get(f"/api/products/{p['id']}", headers=staff).status_code == 200


def test_public_category_filter_by_numeric_id(client, staff):
    _create(client, staff, name='Tote', categoryId=1)
    _create(client, staff, name='Toy', categoryId=3)
    r = client.get('/api/products', params={'category': '3'})
    assert [i['name'] for i in r.json()['items']] == ['Toy']


def test_set_active_failures(client, staff):
    p = _create(client, staff)
    assert client.patch('/api/staff/products/nope/active', json={'isActive': False}, headers=staff).status_code == 404
    assert client.patch(f"/api/staff/products/{p['id']}/active", json={}, headers=staff).status_code == 422
    assert client.patch(f"/api/staff/products/{p['id']}/active", json={'isActive': 'zzz'}, headers=staff).status_code == 422


def test_deactivate_is_idempotent_and_keeps_data(client, staff):
    p = _create(client, staff)
    url = f"/api/staff/products/{p['id']}/active"
    for _ in range(2):
        r = client.patch(url, json={'isActive': False}, headers=staff)
        assert r.status_code == 200 and r.json()['isActive'] is False
    got = client.get(f"/api/staff/products/{p['id']}", headers=staff).json()
    assert got['name'] == 'Tote' and got['stock']['quantity'] == 10


def test_create_missing_and_malformed_body(client, staff):
    assert client.post('/api/staff/products', json={}, headers=staff).status_code == 422
    r = client.post('/api/staff/products', json={'name': 'x', 'categoryId': 'abc', 'priceSen': 'free'}, headers=staff)
    assert r.status_code == 422
    assert client.get('/api/staff/products', headers=staff).json()['total'] == 0


def test_update_validation_failure_leaves_product_unchanged(client, staff):
    p = _create(client, staff)
    r = client.put(f"/api/staff/products/{p['id']}", json={'name': '', 'categoryId': 99, 'priceSen': 0}, headers=staff)
    assert r.status_code == 422
    got = client.get(f"/api/staff/products/{p['id']}", headers=staff).json()
    assert got['name'] == 'Tote' and got['priceSen'] == 3000 and got['category']['id'] == 1


def test_upload_missing_file_and_inactive_product(client, staff):
    p = _create(client, staff)
    url = f"/api/staff/products/{p['id']}/images"
    assert client.post(url, headers=staff).status_code == 422
    client.patch(f"/api/staff/products/{p['id']}/active", json={'isActive': False}, headers=staff)
    r = client.post(url, files={'file': ('a.png', PNG, 'image/png')}, headers=staff)
    assert r.status_code in (201, 404)


def test_upload_empty_file_rejected(client, staff):
    p = _create(client, staff)
    r = client.post(f"/api/staff/products/{p['id']}/images", files={'file': ('a.png', b'', 'image/png')}, headers=staff)
    assert r.status_code == 422
    assert client.get(f"/api/staff/products/{p['id']}", headers=staff).json()['images'] == []


def test_customer_forbidden_for_all_staff_product_actions(client, staff, customer):
    p = _create(client, staff)
    pid = p['id']
    body = {'name': 'Hack', 'categoryId': 1, 'priceSen': 1}
    assert client.get('/api/staff/products', headers=customer).status_code == 403
    assert client.get(f'/api/staff/products/{pid}', headers=customer).status_code == 403
    assert client.post('/api/staff/products', json=body, headers=customer).status_code == 403
    assert client.put(f'/api/staff/products/{pid}', json=body, headers=customer).status_code == 403
    assert client.patch(f'/api/staff/products/{pid}/active', json={'isActive': False}, headers=customer).status_code == 403
    assert client.delete(f'/api/staff/products/{pid}', headers=customer).status_code == 403
    assert client.post(f'/api/staff/products/{pid}/images', files={'file': ('a.png', PNG, 'image/png')},
                       headers=customer).status_code == 403
    # nothing changed
    got = client.get(f'/api/staff/products/{pid}', headers=staff).json()
    assert got['name'] == 'Tote' and got['isActive'] is True
