"""Custom orders: customer side (Req 16.1-16.5, 16.8) and staff management (Req 25.1-25.8, 25.10)."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app import db
from app.modules.users import api as users_api
from app.security import hash_password
from app.time_utils import today_local

PASSWORD = ''.join(['Secret', '123'])
PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 32
TODAY = today_local('Asia/Kuala_Lumpur')


def _login(client, settings, role, email=None):
    email = email or f'{role}@example.com'
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        users_api.create_user(conn, name='U', email=email, password_hash=hash_password(PASSWORD), role=role)
    conn.close()
    token = client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture()
def staff(client, settings):
    return _login(client, settings, 'seller')


@pytest.fixture()
def cust(client, settings):
    return _login(client, settings, 'customer')


def _form(**over):
    data = {'productType': 'Batik bag', 'description': 'A batik tote bag in blue', 'quantity': '2',
            'preferredDate': (TODAY + timedelta(days=10)).isoformat()}
    data.update(over)
    return {k: v for k, v in data.items() if v is not None}


def _create(client, headers, files=None, **over):
    return client.post('/api/custom-orders', data=_form(**over), files=files, headers=headers)


def _images(n, name='a.png', data=PNG):
    return [('images', (name, data, 'image/png')) for _ in range(n)]


def _media_files(settings):
    media = settings.media_dir
    return [p for p in media.iterdir() if p.is_file()] if media.exists() else []


def _notes(settings, email):
    conn = db.connect(settings.database_path)
    rows = conn.execute('SELECT n.type, n.body FROM notifications n JOIN users u ON u.id = n.user_id '
                        'WHERE u.email = ? ORDER BY n.id', (email,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def test_create_list_detail_and_staff_notification(client, staff, cust, settings):
    res = _create(client, cust, files=_images(2))
    assert res.status_code == 201
    body = res.json()
    assert body['status'] == 'submitted' and len(body['imageUrls']) == 2
    assert client.get(f'/api/custom-orders/{body["id"]}', headers=cust).json()['id'] == body['id']
    assert client.get('/api/custom-orders', headers=cust).json()['total'] == 1
    assert [n['type'] for n in _notes(settings, 'seller@example.com')] == ['custom_order']


def test_validation_errors_create_nothing(client, cust, settings):
    res = _create(client, cust, description='short', quantity='0',
                  preferredDate=(TODAY - timedelta(days=1)).isoformat(), productType=None)
    assert res.status_code == 422
    fields = {d['field'] for d in res.json()['error']['details']}
    assert {'description', 'quantity', 'preferredDate', 'productType'} <= fields
    assert _create(client, cust, quantity='1.5').status_code == 422
    assert client.get('/api/custom-orders', headers=cust).json()['total'] == 0


@pytest.mark.parametrize('files', [
    _images(6),
    _images(1) + [('images', ('b.gif', b'GIF89a....', 'image/gif'))],
    _images(1) + [('images', ('big.png', PNG + b'0' * (5 * 1024 * 1024), 'image/png'))],
])
def test_bad_images_store_nothing(client, cust, settings, files):
    assert _create(client, cust, files=files).status_code == 422
    assert _media_files(settings) == []
    assert client.get('/api/custom-orders', headers=cust).json()['total'] == 0


def test_media_owner_and_staff_only(client, staff, cust, settings):
    created = _create(client, cust, files=_images(1)).json()
    url = created['imageUrls'][0]
    assert client.get(url, headers=cust).status_code == 200
    assert client.get(url, headers=staff).status_code == 200
    assert client.get(url).status_code == 401
    other = _login(client, settings, 'customer', 'other@example.com')
    assert client.get(url, headers=other).status_code == 404
    assert client.get(f'/api/custom-orders/{created["id"]}', headers=other).status_code == 404


def test_staff_list_and_filter(client, staff, cust):
    assert client.get('/api/staff/custom-orders', headers=staff).json()['total'] == 0
    a = _create(client, cust).json()['id']
    _create(client, cust)
    client.post(f'/api/staff/custom-orders/{a}/accept', json={'estimatedPriceSen': 5000}, headers=staff)
    assert client.get('/api/staff/custom-orders', headers=staff).json()['total'] == 2
    only = client.get('/api/staff/custom-orders?status=accepted', headers=staff).json()
    assert [i['id'] for i in only['items']] == [a]
    assert client.get('/api/staff/custom-orders?status=bogus', headers=staff).status_code == 422
    assert client.get('/api/staff/custom-orders', headers=cust).status_code == 403


@pytest.mark.parametrize('price', [0, 100_000_000, 'abc', 10.5, None])
def test_accept_invalid_price(client, staff, cust, price):
    oid = _create(client, cust).json()['id']
    res = client.post(f'/api/staff/custom-orders/{oid}/accept', json={'estimatedPriceSen': price}, headers=staff)
    assert res.status_code == 422
    assert client.get(f'/api/custom-orders/{oid}', headers=cust).json()['status'] == 'submitted'


def test_accept_notifies_owner_and_reject_rules(client, staff, cust, settings):
    oid = _create(client, cust).json()['id']
    ok = client.post(f'/api/staff/custom-orders/{oid}/accept', json={'estimatedPriceSen': 99_999_999}, headers=staff)
    assert ok.status_code == 200 and ok.json()['estimatedPriceSen'] == 99_999_999
    owner_notes = [n for n in _notes(settings, 'customer@example.com') if 'is now accepted' in n['body']]
    assert len(owner_notes) == 1
    assert client.post(f'/api/staff/custom-orders/{oid}/reject', json={'reason': 'long enough'},
                       headers=staff).status_code == 409

    rid = _create(client, cust).json()['id']
    assert client.post(f'/api/staff/custom-orders/{rid}/reject', json={'reason': '  abc  '},
                       headers=staff).status_code == 422
    assert client.post(f'/api/staff/custom-orders/{rid}/reject', json={'reason': 'x' * 501},
                       headers=staff).status_code == 422
    done = client.post(f'/api/staff/custom-orders/{rid}/reject', json={'reason': '  too complex  '}, headers=staff)
    assert done.json()['status'] == 'rejected' and done.json()['rejectReason'] == 'too complex'
    again = client.post(f'/api/staff/custom-orders/{rid}/accept', json={'estimatedPriceSen': 100}, headers=staff)
    assert again.status_code == 409


def test_assign_artisan_creates_one_job_and_status_flow(client, staff, cust):
    oid = _create(client, cust).json()['id']
    artisan = client.post('/api/staff/artisans', json={'name': 'Aminah', 'specialisation': 'Batik',
                                                       'availability': 'available'}, headers=staff).json()['id']
    url = f'/api/staff/custom-orders/{oid}/assign-artisan'
    assert client.post(url, json={'artisanId': artisan}, headers=staff).status_code == 409  # not accepted yet
    client.post(f'/api/staff/custom-orders/{oid}/accept', json={'estimatedPriceSen': 1000}, headers=staff)
    assert client.post(url, json={'artisanId': 9999}, headers=staff).status_code == 422
    done = client.post(url, json={'artisanId': artisan}, headers=staff)
    assert done.status_code == 200 and done.json()['productionJobId']
    assert client.post(url, json={'artisanId': artisan}, headers=staff).status_code == 409
    jobs = client.get('/api/production/jobs', headers=staff).json()['items']
    assert [j['customOrderId'] for j in jobs] == [oid]
    assert client.get(f'/api/custom-orders/{oid}', headers=cust).json()['productionLabel'] == 'production_assigned'

    status = f'/api/staff/custom-orders/{oid}/status'
    assert client.post(status, json={'status': 'completed'}, headers=staff).status_code == 409
    assert client.post(status, json={'status': 'in_progress'}, headers=staff).json()['status'] == 'in_progress'
    assert client.post(status, json={'status': 'in_progress'}, headers=staff).status_code == 409
    assert client.post(status, json={'status': 'completed'}, headers=staff).json()['status'] == 'completed'
    assert client.post(status, json={'status': 'bogus'}, headers=staff).status_code == 422


def test_inactive_artisan_rejected(client, staff, cust):
    oid = _create(client, cust).json()['id']
    client.post(f'/api/staff/custom-orders/{oid}/accept', json={'estimatedPriceSen': 1000}, headers=staff)
    artisan = client.post('/api/staff/artisans', json={'name': 'Z', 'specialisation': 'Batik',
                                                       'availability': 'available'}, headers=staff).json()['id']
    conn = db.connect(client.app.state.settings.database_path)
    with db.transaction(conn):
        conn.execute('UPDATE artisans SET is_active = 0 WHERE id = ?', (artisan,))
    conn.close()
    res = client.post(f'/api/staff/custom-orders/{oid}/assign-artisan', json={'artisanId': artisan}, headers=staff)
    assert res.status_code == 422
    assert client.get('/api/production/jobs', headers=staff).json()['total'] == 0
