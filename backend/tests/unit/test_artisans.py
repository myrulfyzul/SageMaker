"""Artisan management: staff CRUD, privacy, warnings and product links (Req 23.1 to 23.8)."""
from __future__ import annotations

import pytest

from app import db
from app.modules.production import api as production_api
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])
BODY = {'name': 'Aminah', 'specialisation': 'Batik', 'availability': 'available', 'story': 'Hand drawn.',
        'phone': '0123456789', 'email': 'aminah@example.com', 'address': '1 Jalan Kain'}


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
    return client.post('/api/staff/artisans', json={**BODY, **over}, headers=staff)


def test_create_get_and_list_with_private_contact(client, staff):
    r = _create(client, staff)
    assert r.status_code == 201
    a = r.json()
    assert a['privateContact'] == {'phone': '0123456789', 'email': 'aminah@example.com', 'address': '1 Jalan Kain'}
    assert a['openJobCount'] == 0 and a['completedJobCount'] == 0 and a['assignedProducts'] == [] and a['warnings'] == []
    got = client.get(f"/api/staff/artisans/{a['id']}", headers=staff).json()
    assert got['name'] == 'Aminah'
    assert client.get('/api/staff/artisans', headers=staff).json()['total'] == 1
    assert client.get('/api/staff/artisans/999', headers=staff).status_code == 404


@pytest.mark.parametrize('over,fields', [
    ({'name': ''}, {'name'}), ({'name': 'x' * 101}, {'name'}), ({'specialisation': '  '}, {'specialisation'}),
    ({'specialisation': 'x' * 101}, {'specialisation'}), ({'availability': 'away'}, {'availability'}),
    ({'story': 'x' * 2001}, {'story'}), ({'name': '', 'availability': 'x'}, {'name', 'availability'}),
])
def test_invalid_fields_rejected_and_nothing_saved(client, staff, over, fields):
    r = _create(client, staff, **over)
    assert r.status_code == 422
    assert fields <= {d['field'] for d in r.json()['error']['details']}
    assert client.get('/api/staff/artisans', headers=staff).json()['total'] == 0


def test_update_keeps_omitted_fields_and_rejects_invalid(client, staff):
    aid = _create(client, staff).json()['id']
    r = client.put(f'/api/staff/artisans/{aid}', json={'name': 'Aminah B', 'specialisation': 'Songket',
                                                       'availability': 'busy'}, headers=staff)
    assert r.status_code == 200
    assert r.json()['name'] == 'Aminah B' and r.json()['privateContact']['phone'] == '0123456789'
    assert r.json()['story'] == 'Hand drawn.'
    bad = client.put(f'/api/staff/artisans/{aid}', json={'name': '', 'specialisation': 'x', 'availability': 'busy'},
                     headers=staff)
    assert bad.status_code == 422
    assert client.get(f'/api/staff/artisans/{aid}', headers=staff).json()['name'] == 'Aminah B'


def test_unavailable_with_open_jobs_saves_with_warning(client, staff, monkeypatch):
    aid = _create(client, staff).json()['id']
    monkeypatch.setattr(production_api, 'open_job_ids', lambda conn, artisan_id: [4, 9])
    monkeypatch.setattr(production_api, 'counts_for_artisan', lambda conn, artisan_id: {'open': 2, 'completed': 5})
    r = client.put(f'/api/staff/artisans/{aid}', json={**BODY, 'availability': 'unavailable'}, headers=staff)
    assert r.status_code == 200
    body = r.json()
    assert body['availability'] == 'unavailable' and body['warnings'][0]['jobIds'] == [4, 9]
    assert body['openJobCount'] == 2 and body['completedJobCount'] == 5
    ok = client.put(f'/api/staff/artisans/{aid}', json={**BODY, 'availability': 'busy'}, headers=staff)
    assert ok.json()['warnings'] == []


def test_public_view_omits_private_fields(client, staff):
    aid = _create(client, staff, availability='busy').json()['id']
    one = client.get(f'/api/artisans/{aid}')
    assert one.status_code == 200
    assert set(one.json()) == {'id', 'publicName', 'specialisation', 'story'}
    assert one.json()['publicName'] == 'Aminah'
    lst = client.get('/api/artisans').json()
    assert lst['total'] == 1 and set(lst['items'][0]) == {'id', 'publicName', 'specialisation', 'story'}
    assert client.get('/api/artisans/999').status_code == 404


def test_private_contact_denied_to_visitors_and_customers(client, settings, staff):
    aid = _create(client, staff).json()['id']
    assert client.get(f'/api/staff/artisans/{aid}').status_code == 401
    customer = _login(client, settings, 'customer')
    for r in (client.get(f'/api/staff/artisans/{aid}', headers=customer), client.get('/api/staff/artisans', headers=customer),
              client.post('/api/staff/artisans', json=BODY, headers=customer)):
        assert r.status_code == 403 and '0123456789' not in r.text


def test_link_and_unlink_product(client, staff):
    aid = _create(client, staff).json()['id']
    pid = client.post('/api/staff/products', json={'name': 'Tote', 'categoryId': 1, 'priceSen': 3000, 'stock': 1},
                      headers=staff).json()['id']
    r = client.put(f'/api/staff/products/{pid}/artisan', json={'artisanId': aid}, headers=staff)
    assert r.status_code == 200 and [p['id'] for p in r.json()['assignedProducts']] == [pid]
    assert client.get(f"/api/staff/artisans/{aid}", headers=staff).json()['assignedProducts'][0]['name'] == 'Tote'
    assert client.get(f'/api/products/{pid}').json()['artisan'] == {'id': aid, 'name': 'Aminah'}
    r = client.put(f'/api/staff/products/{pid}/artisan', json={'artisanId': None}, headers=staff)
    assert r.status_code == 200 and r.json()['assignedProducts'] == []
    assert client.get(f'/api/products/{pid}').json()['artisan'] is None
    assert client.put(f'/api/staff/products/{pid}/artisan', json={'artisanId': 999}, headers=staff).status_code == 422
    assert client.put('/api/staff/products/nope/artisan', json={'artisanId': aid}, headers=staff).status_code == 404
