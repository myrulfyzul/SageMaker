"""Extra cases for artisans, production and custom orders (Req 6.7, 6.8, 16.8, 23.8, 24.6, 25.10, 31.1)."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app import db
from app.modules.artisans import api as artisans_api
from app.modules.orders import api as orders_api
from app.modules.orders.schemas import NewOrder, NewOrderLine
from app.modules.production import api as production_api
from app.modules.users import api as users_api
from app.security import hash_password
from app.time_utils import today_local

PASSWORD = ''.join(['Secret', '123'])
ARTISAN = {'name': 'Aminah', 'specialisation': 'Batik', 'availability': 'available'}
TODAY = today_local('Asia/Kuala_Lumpur')


def _login(client, settings, role, email=None):
    email = email or f'{role}@example.com'
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        uid = users_api.create_user(conn, name='U', email=email, password_hash=hash_password(PASSWORD), role=role)['id']
    conn.close()
    token = client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
    return {'Authorization': f'Bearer {token}'}, uid


@pytest.fixture()
def staff(client, settings):
    return _login(client, settings, 'seller')[0]


@pytest.fixture()
def cust(client, settings):
    return _login(client, settings, 'customer')[0]


@pytest.fixture()
def conn(client, settings):
    c = db.connect(settings.database_path)
    yield c
    c.close()


def _jobs(conn, n=2):
    with db.transaction(conn):
        order, _ = orders_api.create_order(conn, NewOrder(
            user_id=1, idempotency_key='k', customer_name='A B', email='a@x.com', phone='0123456789',
            delivery_address='1 Road', payment_method='card', payment_status='paid', shipping_fee_sen=800,
            lines=[NewOrderLine(product_id=f'p{i}', variation_id=None, sku_key=f'p{i}', name='T', unit_price_sen=1000,
                                quantity=1) for i in range(n)]))
        return production_api.create_jobs_for_order(conn, order['id'])


def _artisan(client, staff, **over):
    return client.post('/api/staff/artisans', json={**ARTISAN, **over}, headers=staff).json()['id']


def _assign(client, staff, jid, aid):
    return client.post(f'/api/production/jobs/{jid}/assign', json={
        'artisanId': aid, 'quantity': 1, 'deadline': (TODAY + timedelta(days=3)).isoformat()}, headers=staff)


def _custom(client, headers, **over):
    data = {'productType': 'Bag', 'description': 'A batik tote bag in blue', 'quantity': '1',
            'preferredDate': (TODAY + timedelta(days=9)).isoformat(), **over}
    return client.post('/api/custom-orders', data=data, headers=headers)


# ---- artisans ----

def test_artisan_update_unknown_404_and_visitor_cannot_create(client, staff):
    assert client.put('/api/staff/artisans/999', json=ARTISAN, headers=staff).status_code == 404
    assert client.post('/api/staff/artisans', json=ARTISAN).status_code == 401
    assert client.get('/api/staff/artisans', headers=staff).json()['total'] == 0


def test_artisan_update_unauthorised_roles_change_nothing(client, settings, staff):
    aid = _artisan(client, staff)
    cust_headers, _ = _login(client, settings, 'customer')
    r = client.put(f'/api/staff/artisans/{aid}', json={**ARTISAN, 'name': 'Hacked'}, headers=cust_headers)
    assert r.status_code == 403
    assert client.get(f'/api/staff/artisans/{aid}', headers=staff).json()['name'] == 'Aminah'


# ---- production: assigned and non-assigned artisan ----

def test_artisan_progress_on_unassigned_job_and_unlinked_artisan_forbidden(client, settings, staff, conn):
    ids = _jobs(conn)
    headers, uid = _login(client, settings, 'artisan')  # not linked to any artisan record
    for jid in ids:
        r = client.post(f'/api/production/jobs/{jid}/progress', json={'percent': 10}, headers=headers)
        assert r.status_code == 403
        assert client.get(f'/api/production/jobs/{jid}', headers=headers).status_code == 403
    aid = _artisan(client, staff)
    with db.transaction(conn):
        artisans_api.link_user(conn, aid, uid)
    # linked, but job 0 is still unassigned: still forbidden
    r = client.post(f'/api/production/jobs/{ids[0]}/progress', json={'percent': 10}, headers=headers)
    assert r.status_code == 403
    assert conn.execute('SELECT COUNT(*) FROM production_progress').fetchone()[0] == 0


def test_assigned_artisan_progress_records_history_and_validates(client, settings, staff, conn):
    ids = _jobs(conn, 1)
    headers, uid = _login(client, settings, 'artisan')
    aid = _artisan(client, staff)
    with db.transaction(conn):
        artisans_api.link_user(conn, aid, uid)
    _assign(client, staff, ids[0], aid)
    url = f'/api/production/jobs/{ids[0]}/progress'
    assert client.post(url, json={'percent': 101}, headers=headers).status_code == 422
    assert client.post(url, json={'percent': 30, 'note': 'dyed'}, headers=headers).status_code == 200
    assert client.post(url, json={'percent': 70}, headers=headers).json()['progressPercent'] == 70
    detail = client.get(f'/api/production/jobs/{ids[0]}', headers=headers).json()
    assert [p['percent'] for p in detail['progressHistory']] == [30, 70]


def test_progress_unknown_job_404_and_staff_changes_status_only(client, settings, staff, conn):
    assert client.post('/api/production/jobs/9999/progress', json={'percent': 5}, headers=staff).status_code == 404
    assert client.get('/api/production/jobs/9999', headers=staff).status_code == 404
    assert client.post('/api/production/jobs/9999/status', json={'status': 'in_production'},
                       headers=staff).status_code == 404
    assert _assign(client, staff, 9999, _artisan(client, staff)).status_code == 404


def test_other_artisan_cannot_progress_assigned_job(client, settings, staff, conn):
    ids = _jobs(conn, 1)
    owner = _artisan(client, staff)
    _assign(client, staff, ids[0], owner)
    headers, uid = _login(client, settings, 'artisan', 'other-artisan@example.com')
    other = _artisan(client, staff, name='Other')
    with db.transaction(conn):
        artisans_api.link_user(conn, other, uid)
    r = client.post(f'/api/production/jobs/{ids[0]}/progress', json={'percent': 50}, headers=headers)
    assert r.status_code == 403
    assert conn.execute('SELECT progress_percent FROM production_jobs WHERE id = ?', (ids[0],)).fetchone()[0] in (0, None)


# ---- custom orders ----

def test_custom_order_requires_customer_login(client, staff):
    assert _custom(client, {}).status_code == 401
    assert _custom(client, staff).status_code == 403  # staff cannot submit
    assert client.get('/api/staff/custom-orders', headers=staff).json()['total'] == 0


def test_accept_reject_unknown_and_customer_forbidden(client, staff, cust):
    oid = _custom(client, cust).json()['id']
    for action, body in (('accept', {'estimatedPriceSen': 100}), ('reject', {'reason': 'not feasible'})):
        assert client.post(f'/api/staff/custom-orders/9999/{action}', json=body, headers=staff).status_code == 404
        assert client.post(f'/api/staff/custom-orders/{oid}/{action}', json=body, headers=cust).status_code == 403
    assert client.get(f'/api/custom-orders/{oid}', headers=cust).json()['status'] == 'submitted'


def test_invalid_transitions_from_submitted_and_terminal_states(client, staff, cust):
    oid = _custom(client, cust).json()['id']
    status_url = f'/api/staff/custom-orders/{oid}/status'
    # submitted -> in_progress / completed not allowed
    for target in ('in_progress', 'completed'):
        assert client.post(status_url, json={'status': target}, headers=staff).status_code == 409
    client.post(f'/api/staff/custom-orders/{oid}/reject', json={'reason': 'not feasible'}, headers=staff)
    # rejected is terminal
    assert client.post(f'/api/staff/custom-orders/{oid}/reject', json={'reason': 'again again'},
                       headers=staff).status_code == 409
    assert client.post(status_url, json={'status': 'in_progress'}, headers=staff).status_code == 409
    assert client.get(f'/api/custom-orders/{oid}', headers=cust).json()['status'] == 'rejected'
