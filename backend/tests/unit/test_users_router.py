"""Users routers: /api/me profile and addresses, admin role change and deactivation."""
from __future__ import annotations

from app import db
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])

ADDRESS = {'recipientName': 'Aisha', 'phone': '0123456789', 'line1': '1 Jalan A', 'postcode': '50000',
           'city': 'KL', 'state': 'WP'}


def _h(token):
    return {'Authorization': f'Bearer {token}'}


def _customer(client, email='a@example.com'):
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    r = client.post('/api/auth/login', json={'email': email, 'password': PASSWORD})
    return r.json()['token'], r.json()['user']['id']


def _admin(client, settings):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        users_api.create_user(conn, name='Root', email='admin@example.com', password_hash=hash_password(PASSWORD),
                              role='admin')
    conn.close()
    return client.post('/api/auth/login', json={'email': 'admin@example.com', 'password': PASSWORD}).json()['token']


def test_profile_and_address_flow(client):
    token, _ = _customer(client)
    assert client.get('/api/me', headers=_h(token)).json()['email'] == 'a@example.com'
    r = client.put('/api/me', headers=_h(token), json={'name': 'New', 'phone': '0123456789'})
    assert r.status_code == 200 and r.json()['name'] == 'New'
    assert client.put('/api/me', headers=_h(token), json={'name': '', 'phone': '1'}).status_code == 422

    a1 = client.post('/api/me/addresses', headers=_h(token), json=ADDRESS)
    assert a1.status_code == 201
    a2 = client.post('/api/me/addresses', headers=_h(token), json={**ADDRESS, 'isDefault': True}).json()
    assert client.put(f"/api/me/addresses/{a1.json()['id']}/default", headers=_h(token)).json()['isDefault']
    listed = client.get('/api/me/addresses', headers=_h(token)).json()
    assert [a['isDefault'] for a in listed].count(True) == 1
    assert client.put(f"/api/me/addresses/{a2['id']}", headers=_h(token), json={**ADDRESS, 'city': 'PJ'}).json()['city'] == 'PJ'
    assert client.delete(f"/api/me/addresses/{a2['id']}", headers=_h(token)).status_code == 204


def test_foreign_and_missing_addresses_give_identical_404(client):
    t1, _ = _customer(client)
    t2, _ = _customer(client, 'b@example.com')
    foreign = client.post('/api/me/addresses', headers=_h(t1), json=ADDRESS).json()['id']
    for call in (lambda i: client.put(f'/api/me/addresses/{i}', headers=_h(t2), json=ADDRESS),
                 lambda i: client.put(f'/api/me/addresses/{i}/default', headers=_h(t2)),
                 lambda i: client.delete(f'/api/me/addresses/{i}', headers=_h(t2))):
        a, b = call(foreign), call(99999)
        assert a.status_code == b.status_code == 404 and a.json() == b.json()


def test_admin_only_endpoints_and_deactivation_revokes_sessions(client, settings):
    token, uid = _customer(client)
    assert client.patch(f'/api/users/{uid}/role', headers=_h(token), json={'role': 'admin'}).status_code == 403
    assert client.post(f'/api/users/{uid}/deactivate', headers=_h(token)).status_code == 403
    assert client.get('/api/me').status_code == 401

    admin = _admin(client, settings)
    assert client.get('/api/me', headers=_h(admin)).status_code == 403
    assert client.patch(f'/api/users/{uid}/role', headers=_h(admin), json={'role': 'bogus'}).status_code == 422
    assert client.patch('/api/users/9999/role', headers=_h(admin), json={'role': 'seller'}).status_code == 404
    assert client.patch(f'/api/users/{uid}/role', headers=_h(admin), json={'role': 'customer'}).status_code == 200

    assert client.post('/api/users/9999/deactivate', headers=_h(admin)).status_code == 404
    assert client.post(f'/api/users/{uid}/deactivate', headers=_h(admin)).status_code == 200
    assert client.get('/api/me', headers=_h(token)).status_code == 401
