"""Production tracking over real jobs (Req 6.7, 6.8, 24.1 to 24.11) and the artisans warning/counts that use it."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app import db
from app.modules.artisans import api as artisans_api
from app.modules.inventory import api as inventory_api
from app.modules.orders import api as orders_api
from app.modules.orders.schemas import NewOrder, NewOrderLine
from app.modules.production import api as production_api
from app.modules.users import api as users_api
from app.security import hash_password
from app.time_utils import today_local

PASSWORD = ''.join(['Secret', '123'])
ARTISAN = {'name': 'Aminah', 'specialisation': 'Batik', 'availability': 'available'}


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
def conn(client, settings):  # `client` first so migrations have run
    c = db.connect(settings.database_path)
    yield c
    c.close()


def _order(conn, lines, key='k1'):
    with db.transaction(conn):
        order, _ = orders_api.create_order(conn, NewOrder(
            user_id=1, idempotency_key=key, customer_name='A B', email='a@x.com', phone='0123456789',
            delivery_address='1 Road', payment_method='card', payment_status='paid', shipping_fee_sen=800,
            lines=[NewOrderLine(product_id=pid, variation_id=None, sku_key=pid, name='Thing', unit_price_sen=1000,
                                quantity=qty) for pid, qty in lines]))
    return order


def _job(conn, qty=2, pid='p1'):
    order = _order(conn, [(pid, qty)])
    with db.transaction(conn):
        return order, production_api.create_jobs_for_order(conn, order['id'])


def _artisan(client, staff, **over):
    return client.post('/api/staff/artisans', json={**ARTISAN, **over}, headers=staff).json()['id']


def _assign(client, staff, job_id, artisan_id, **over):
    body = {'artisanId': artisan_id, 'quantity': 3, 'deadline': (today_local('Asia/Kuala_Lumpur') + timedelta(days=5)).isoformat(),
            **over}
    return client.post(f'/api/production/jobs/{job_id}/assign', json=body, headers=staff)


def _status(client, staff, job_id, status):
    return client.post(f'/api/production/jobs/{job_id}/status', json={'status': status}, headers=staff)


def test_create_jobs_for_order_made_to_order_or_short_stock(client, staff, conn):
    mto = client.post('/api/staff/products', json={'name': 'Bag', 'categoryId': 1, 'priceSen': 3000, 'stock': 50,
                                                   'madeToOrder': True}, headers=staff).json()['id']
    stocked = client.post('/api/staff/products', json={'name': 'Tote', 'categoryId': 1, 'priceSen': 3000,
                                                       'stock': 5}, headers=staff).json()['id']
    with db.transaction(conn):
        inventory_api.adjust(conn, stocked, None, -3, 'sold', None)  # 2 left after "checkout"
    order = _order(conn, [(mto, 1), (stocked, 2), (stocked, 3)])
    with db.transaction(conn):
        ids = production_api.create_jobs_for_order(conn, order['id'])
        assert production_api.create_jobs_for_order(conn, order['id']) == []  # repeat is harmless
    rows = conn.execute('SELECT product_id, quantity, status, order_line_id FROM production_jobs ORDER BY id').fetchall()
    assert len(ids) == 2
    assert [(r['product_id'], r['quantity'], r['status']) for r in rows] == [
        (mto, 1, 'order_confirmed'), (stocked, 3, 'order_confirmed')]


def test_assign_validations_and_transitions(client, staff, conn):
    _, ids = _job(conn)
    jid = ids[0]
    aid = _artisan(client, staff)
    today = today_local('Asia/Kuala_Lumpur')
    for over, field in [({'deadline': (today - timedelta(days=1)).isoformat()}, 'deadline'),
                        ({'deadline': 'soon'}, 'deadline'), ({'quantity': 0}, 'quantity'),
                        ({'quantity': 1000000}, 'quantity'), ({'priority': 'asap'}, 'priority'),
                        ({'notes': 'x' * 1001}, 'notes'), ({'artisanId': 999}, 'artisanId')]:
        r = _assign(client, staff, jid, aid, **over)
        assert r.status_code == 422 and field in {d['field'] for d in r.json()['error']['details']}, over
    assert conn.execute('SELECT status FROM production_jobs WHERE id = ?', (jid,)).fetchone()[0] == 'order_confirmed'
    ok = _assign(client, staff, jid, aid, deadline=today.isoformat(), quantity=999999, notes='n')
    body = ok.json()
    assert ok.status_code == 200 and body['status'] == 'production_assigned' and body['priority'] == 'normal'
    assert body['quantity'] == 999999 and body['artisanId'] == aid and body['overdue'] is False
    assert _assign(client, staff, jid, aid).status_code == 409  # only from order_confirmed
    # sequence
    bad = _status(client, staff, jid, 'completed')
    assert bad.status_code == 409
    assert bad.json()['error']['details'] == [{'current': 'production_assigned', 'requested': 'completed'}]
    for nxt in ('in_production', 'quality_checking', 'in_production', 'quality_checking', 'completed'):
        assert _status(client, staff, jid, nxt).status_code == 200
    assert _status(client, staff, jid, 'in_production').status_code == 409
    assert _status(client, staff, jid, 'nonsense').status_code == 422


def test_ready_for_fulfilment_notifies_staff_and_leaves_order_status(client, staff, conn):
    order, ids = _job(conn)
    jid = ids[0]
    _assign(client, staff, jid, _artisan(client, staff))
    for s in ('in_production', 'quality_checking', 'completed', 'ready_for_fulfilment'):
        assert _status(client, staff, jid, s).status_code == 200
    n = conn.execute("SELECT COUNT(*) FROM notifications WHERE type = 'production'").fetchone()[0]
    assert n == 1
    assert orders_api.get_order(conn, order['id'])['status'] == order['status']
    assert len(orders_api.get_order(conn, order['id'])['history']) == len(order['history'])


def test_progress_validation_and_history(client, staff, conn):
    _, ids = _job(conn)
    jid = ids[0]
    for bad in ({'percent': -1}, {'percent': 101}, {'percent': 50.5}, {'percent': '5'}, {'percent': 5, 'note': 'x' * 501}):
        assert client.post(f'/api/production/jobs/{jid}/progress', json=bad, headers=staff).status_code == 422
    assert conn.execute('SELECT COUNT(*) FROM production_progress').fetchone()[0] == 0
    r = client.post(f'/api/production/jobs/{jid}/progress', json={'percent': 40, 'note': 'cut'}, headers=staff)
    assert r.status_code == 200 and r.json()['progressPercent'] == 40
    detail = client.get(f'/api/production/jobs/{jid}', headers=staff).json()
    assert [(p['percent'], p['note']) for p in detail['progressHistory']] == [(40, 'cut')]
    assert detail['progressHistory'][0]['createdAt']


def test_list_filters_and_board_view_and_overdue(client, staff, conn):
    order = _order(conn, [('a', 1), ('b', 1), ('c', 1)])
    with db.transaction(conn):
        conn.execute('UPDATE order_lines SET quantity = 1')  # no stock rows, so each line exceeds zero stock
        ids = production_api.create_jobs_for_order(conn, order['id'])
    a1, a2 = _artisan(client, staff), _artisan(client, staff, name='Bee')
    _assign(client, staff, ids[0], a1, priority='urgent')
    _assign(client, staff, ids[1], a2, priority='low')
    conn.execute("UPDATE production_jobs SET deadline = '2000-01-01' WHERE id = ?", (ids[0],))
    conn.commit()
    items = client.get('/api/production/jobs', headers=staff).json()['items']
    assert len(items) == 3 and {j['id']: j['overdue'] for j in items} == {ids[0]: True, ids[1]: False, ids[2]: False}
    one = client.get(f'/api/production/jobs?status=production_assigned&artisan_id={a1}&priority=urgent', headers=staff)
    assert [j['id'] for j in one.json()['items']] == [ids[0]]
    assert client.get(f'/api/production/jobs?artisan_id={a1}&priority=low', headers=staff).json()['total'] == 0
    board = client.get('/api/production/jobs?view=board', headers=staff).json()
    cols = {c['status']: [j['id'] for j in c['items']] for c in board['columns']}
    assert len(cols) == 6 and sorted(cols['production_assigned']) == sorted(ids[:2]) and cols['order_confirmed'] == [ids[2]]
    assert client.get('/api/production/jobs?status=bad', headers=staff).status_code == 422
    # overdue stops once completed
    for s in ('in_production', 'quality_checking', 'completed'):
        _status(client, staff, ids[0], s)
    assert client.get(f'/api/production/jobs/{ids[0]}', headers=staff).json()['overdue'] is False


def test_manual_create(client, staff, conn):
    order = _order(conn, [('p9', 4)])
    line_id = order['lines'][0]['id']
    r = client.post('/api/production/jobs', json={'orderId': order['id'], 'orderLineId': line_id}, headers=staff)
    assert r.status_code == 201 and r.json()['status'] == 'order_confirmed' and r.json()['quantity'] == 4
    assert client.post('/api/production/jobs', json={'orderId': 'SM-NOPE', 'orderLineId': 1}, headers=staff).status_code == 404
    assert client.post('/api/production/jobs', json={'orderId': order['id'], 'orderLineId': 99999},
                       headers=staff).status_code == 422


def test_artisan_user_scoping(client, settings, staff, conn):
    _, ids = _job(conn)
    other_order = _order(conn, [('q', 1)], key='k2')
    with db.transaction(conn):
        other_ids = production_api.create_jobs_for_order(conn, other_order['id'])
    mine, other = ids[0], other_ids[0]
    headers, uid = _login(client, settings, 'artisan')
    aid = _artisan(client, staff)
    with db.transaction(conn):
        artisans_api.link_user(conn, aid, uid)
    assert artisans_api.artisan_id_for_user(conn, uid) == aid
    _assign(client, staff, mine, aid)
    _assign(client, staff, other, _artisan(client, staff, name='Other'))
    assert [j['id'] for j in client.get('/api/production/jobs', headers=headers).json()['items']] == [mine]
    assert client.get(f'/api/production/jobs/{mine}', headers=headers).status_code == 200
    for r in (client.get(f'/api/production/jobs/{other}', headers=headers),
              client.post(f'/api/production/jobs/{other}/progress', json={'percent': 5}, headers=headers),
              client.get('/api/staff/artisans', headers=headers),
              client.post(f'/api/production/jobs/{mine}/status', json={'status': 'in_production'}, headers=headers),
              client.post('/api/production/jobs', json={'orderId': 'x', 'orderLineId': 1}, headers=headers)):
        assert r.status_code == 403
    assert conn.execute('SELECT COUNT(*) FROM production_progress').fetchone()[0] == 0
    ok = client.post(f'/api/production/jobs/{mine}/progress', json={'percent': 60}, headers=headers)
    assert ok.status_code == 200 and ok.json()['progressPercent'] == 60
    customer, _ = _login(client, settings, 'customer')
    assert client.get('/api/production/jobs', headers=customer).status_code == 403
    assert client.get('/api/production/jobs').status_code == 401


def test_artisan_warning_and_counts_use_real_jobs(client, staff, conn):
    order = _order(conn, [('a', 1), ('b', 1), ('c', 1)])
    with db.transaction(conn):
        ids = production_api.create_jobs_for_order(conn, order['id'])
    aid = _artisan(client, staff)
    for jid in ids:
        _assign(client, staff, jid, aid)
    for s in ('in_production', 'quality_checking', 'completed'):
        _status(client, staff, ids[0], s)
    _status(client, staff, ids[1], 'in_production')
    assert production_api.counts_for_artisan(conn, aid) == {'open': 2, 'completed': 1}
    assert production_api.open_job_ids(conn, aid) == sorted(ids[1:])
    assert production_api.open_job_count(conn) == 2
    profile = client.get(f'/api/staff/artisans/{aid}', headers=staff).json()
    assert profile['openJobCount'] == 2 and profile['completedJobCount'] == 1
    r = client.put(f'/api/staff/artisans/{aid}', json={**ARTISAN, 'availability': 'unavailable'}, headers=staff).json()
    assert r['availability'] == 'unavailable' and r['warnings'][0]['jobIds'] == sorted(ids[1:])
    for s in ('quality_checking', 'completed'):
        _status(client, staff, ids[1], s)
    _status(client, staff, ids[2], 'in_production')
    _status(client, staff, ids[2], 'quality_checking')
    _status(client, staff, ids[2], 'completed')
    _status(client, staff, ids[2], 'ready_for_fulfilment')
    assert production_api.counts_for_artisan(conn, aid) == {'open': 0, 'completed': 3}
    again = client.put(f'/api/staff/artisans/{aid}', json={**ARTISAN, 'availability': 'unavailable'}, headers=staff).json()
    assert again['warnings'] == []
