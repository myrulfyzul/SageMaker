"""Endpoint-level success and failure paths for auth, profile and addresses (Req 4.1, 4.3, 5.1, 5.2, 6.1, 6.2,
7.2, 7.8, 31.1). Complements test_auth_module.py and test_users_router.py."""
from __future__ import annotations

import pytest

from app import db
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])
WRONG = ''.join(['Wrong', '1234'])

ADDRESS = {'recipientName': 'Aisha', 'phone': '0123456789', 'line1': '1 Jalan A', 'postcode': '50000',
           'city': 'KL', 'state': 'WP'}


def _h(token):
    return {'Authorization': f'Bearer {token}'}


def _customer(client, email='a@example.com'):
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    return client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']


def _staff_token(client, settings, role):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        users_api.create_user(conn, name=role, email=f'{role}@example.com',
                              password_hash=hash_password(PASSWORD), role=role)
    conn.close()
    return client.post('/api/auth/login', json={'email': f'{role}@example.com', 'password': PASSWORD}).json()['token']


# ---- auth ----------------------------------------------------------------------------------------

def test_register_success_returns_201_without_secrets(client):
    r = client.post('/api/auth/register', json={'name': 'Aisha', 'email': 'a@example.com', 'password': PASSWORD})
    assert r.status_code == 201
    assert set(r.json()) >= {'id', 'name', 'email', 'role'}
    assert PASSWORD not in r.text


def test_register_missing_fields_is_422(client):
    assert client.post('/api/auth/register', json={}).status_code == 422


def test_login_missing_fields_is_422(client):
    assert client.post('/api/auth/login', json={'email': 'a@example.com'}).status_code == 422


def test_login_success_response_shape(client):
    _customer(client)
    r = client.post('/api/auth/login', json={'email': 'A@Example.com', 'password': PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body['token'] and body['expiresAt'] and body['user']['email'] == 'a@example.com'
    assert PASSWORD not in r.text


def test_logout_without_token_is_401(client):
    assert client.post('/api/auth/logout').status_code == 401


def test_logout_twice_second_is_401_and_other_session_survives(client):
    _customer(client)
    t1 = client.post('/api/auth/login', json={'email': 'a@example.com', 'password': PASSWORD}).json()['token']
    t2 = client.post('/api/auth/login', json={'email': 'a@example.com', 'password': PASSWORD}).json()['token']
    assert client.post('/api/auth/logout', headers=_h(t1)).status_code == 204
    assert client.post('/api/auth/logout', headers=_h(t1)).status_code == 401
    assert client.get('/api/auth/session', headers=_h(t2)).status_code == 200


def test_session_response_has_no_password_hash(client):
    token = _customer(client)
    r = client.get('/api/auth/session', headers=_h(token))
    assert r.status_code == 200
    assert 'hash' not in r.text.lower() and PASSWORD not in r.text


# ---- profile: 401 / 403 / validation ---------------------------------------------------------------

@pytest.mark.parametrize('method,path,body', [
    ('get', '/api/me', None),
    ('put', '/api/me', {'name': 'x', 'phone': '0123456789'}),
    ('get', '/api/me/addresses', None),
    ('post', '/api/me/addresses', ADDRESS),
    ('put', '/api/me/addresses/1', ADDRESS),
    ('put', '/api/me/addresses/1/default', None),
    ('delete', '/api/me/addresses/1', None),
])
def test_me_endpoints_require_authentication(client, method, path, body):
    kwargs = {'json': body} if body is not None else {}
    assert getattr(client, method)(path, **kwargs).status_code == 401
    assert getattr(client, method)(path, headers=_h('bogus'), **kwargs).status_code == 401


@pytest.mark.parametrize('role', ['admin', 'seller', 'artisan'])
def test_me_endpoints_forbidden_for_non_customer_roles(client, settings, role):
    token = _staff_token(client, settings, role)
    assert client.get('/api/me', headers=_h(token)).status_code == 403
    assert client.get('/api/me/addresses', headers=_h(token)).status_code == 403
    assert client.post('/api/me/addresses', headers=_h(token), json=ADDRESS).status_code == 403


@pytest.mark.parametrize('payload', [
    {'name': 'x', 'phone': '123'},
    {'name': 'x', 'phone': 'abcdefgh'},
    {'name': '   ', 'phone': '0123456789'},
    {'name': 'x'},
    {'name': 'x', 'phone': '0123456789', 'role': 'admin'},
])
def test_profile_update_invalid_is_422_and_unchanged(client, payload):
    token = _customer(client)
    assert client.put('/api/me', headers=_h(token), json=payload).status_code == 422
    assert client.get('/api/me', headers=_h(token)).json()['name'] == 'Aisha'


def test_profile_update_persists(client):
    token = _customer(client)
    client.put('/api/me', headers=_h(token), json={'name': ' New ', 'phone': '0123456789'})
    me = client.get('/api/me', headers=_h(token)).json()
    assert me['name'] == 'New' and me['phone'] == '0123456789' and me['role'] == 'customer'


# ---- addresses -------------------------------------------------------------------------------------

@pytest.mark.parametrize('override', [
    {'postcode': '1234'},
    {'postcode': '123456'},
    {'postcode': 'abcde'},
    {'phone': '12'},
    {'recipientName': ''},
    {'line1': ''},
    {'city': ''},
    {'state': ''},
])
def test_address_invalid_is_422_and_nothing_stored(client, override):
    token = _customer(client)
    r = client.post('/api/me/addresses', headers=_h(token), json={**ADDRESS, **override})
    assert r.status_code == 422
    assert client.get('/api/me/addresses', headers=_h(token)).json() == []


def test_address_update_invalid_is_422_and_unchanged(client):
    token = _customer(client)
    aid = client.post('/api/me/addresses', headers=_h(token), json=ADDRESS).json()['id']
    r = client.put(f'/api/me/addresses/{aid}', headers=_h(token), json={**ADDRESS, 'postcode': '1'})
    assert r.status_code == 422
    assert client.get('/api/me/addresses', headers=_h(token)).json()[0]['postcode'] == '50000'


def test_address_create_response_and_optional_line2(client):
    token = _customer(client)
    r = client.post('/api/me/addresses', headers=_h(token), json={**ADDRESS, 'line2': ''})
    assert r.status_code == 201
    assert r.json()['line2'] is None and r.json()['isDefault'] is False


def test_addresses_are_isolated_per_user(client):
    t1 = _customer(client)
    t2 = _customer(client, 'b@example.com')
    client.post('/api/me/addresses', headers=_h(t1), json=ADDRESS)
    assert len(client.get('/api/me/addresses', headers=_h(t1)).json()) == 1
    assert client.get('/api/me/addresses', headers=_h(t2)).json() == []


def test_foreign_address_is_not_modified_by_other_user(client):
    t1 = _customer(client)
    t2 = _customer(client, 'b@example.com')
    aid = client.post('/api/me/addresses', headers=_h(t1), json=ADDRESS).json()['id']
    client.put(f'/api/me/addresses/{aid}', headers=_h(t2), json={**ADDRESS, 'city': 'Hacked'})
    client.delete(f'/api/me/addresses/{aid}', headers=_h(t2))
    listed = client.get('/api/me/addresses', headers=_h(t1)).json()
    assert len(listed) == 1 and listed[0]['city'] == 'KL'


def test_deleted_address_then_404_identical_to_missing(client):
    token = _customer(client)
    aid = client.post('/api/me/addresses', headers=_h(token), json=ADDRESS).json()['id']
    assert client.delete(f'/api/me/addresses/{aid}', headers=_h(token)).status_code == 204
    again = client.delete(f'/api/me/addresses/{aid}', headers=_h(token))
    missing = client.delete('/api/me/addresses/99999', headers=_h(token))
    assert again.status_code == missing.status_code == 404
    assert again.json() == missing.json()


def test_update_with_is_default_makes_single_default(client):
    token = _customer(client)
    a1 = client.post('/api/me/addresses', headers=_h(token), json={**ADDRESS, 'isDefault': True}).json()['id']
    a2 = client.post('/api/me/addresses', headers=_h(token), json=ADDRESS).json()['id']
    r = client.put(f'/api/me/addresses/{a2}', headers=_h(token), json={**ADDRESS, 'isDefault': True})
    assert r.json()['isDefault'] is True
    flags = {a['id']: a['isDefault'] for a in client.get('/api/me/addresses', headers=_h(token)).json()}
    assert flags == {a1: False, a2: True}


# ---- admin-only endpoints: unauthenticated and role errors -----------------------------------------

def test_admin_endpoints_unauthenticated_401_and_staff_non_admin_403(client, settings):
    assert client.patch('/api/users/1/role', json={'role': 'seller'}).status_code == 401
    assert client.post('/api/users/1/deactivate').status_code == 401
    seller = _staff_token(client, settings, 'seller')
    assert client.patch('/api/users/1/role', headers=_h(seller), json={'role': 'admin'}).status_code == 403
    assert client.post('/api/users/1/deactivate', headers=_h(seller)).status_code == 403
