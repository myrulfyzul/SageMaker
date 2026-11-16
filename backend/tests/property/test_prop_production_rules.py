"""Property 48: Production and artisan rules.

**Validates: Requirements 24.1, 24.3, 24.6, 24.7, 24.8, 24.9, 24.13**

For any set of Production_Jobs: the overdue flag is true iff today is after the deadline and the status is neither
`completed` nor `ready_for_fulfilment`; status, Artisan and priority filters return exactly the jobs matching all
supplied filters; progress is accepted iff it is a whole number 0 to 100 from Staff or the assigned Artisan_User;
deadlines before today are rejected; confirming an Order creates one job per qualifying line.
"""
from __future__ import annotations

import atexit
import itertools
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app
from app.modules.artisans import api as artisans_api
from app.modules.orders import api as orders_api
from app.modules.orders.schemas import NewOrder, NewOrderLine
from app.modules.production import api as production_api
from app.modules.production import repository as repo
from app.modules.production import service
from app.modules.users import api as users_api
from app.security import hash_password
from app.time_utils import today_local

PASSWORD = ''.join(['Secret', '123'])
PROFILE = dict(max_examples=30, deadline=None, suppress_health_check=list(HealthCheck))
_counter = itertools.count()

STATUS = st.sampled_from(service.STATUSES)
PRIORITY = st.sampled_from(service.PRIORITIES)


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='production_prop_'))
        self.settings = Settings(database_path=self.dir / 't.sqlite3', media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(self.settings))
        self.client = self.client_cm.__enter__()
        self.conn = db.connect(self.settings.database_path)
        self.tz = self.settings.app_timezone
        self.staff = self._login('seller')[0]
        self.artisan_headers, artisan_uid = self._login('artisan')
        self.other_headers, other_uid = self._login('artisan')
        self.artisan_ids = [self._artisan(f'Maker {i}') for i in range(3)]
        with db.transaction(self.conn):
            artisans_api.link_user(self.conn, self.artisan_ids[0], artisan_uid)
            artisans_api.link_user(self.conn, self.artisan_ids[1], other_uid)

    def _login(self, role):
        email = f'{role}{next(_counter)}@example.com'
        with db.transaction(self.conn):
            uid = users_api.create_user(self.conn, name='U', email=email, password_hash=hash_password(PASSWORD),
                                        role=role)['id']
        token = self.client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
        return {'Authorization': f'Bearer {token}'}, uid

    def _artisan(self, name):
        r = self.client.post('/api/staff/artisans', json={'name': name, 'specialisation': 'Batik',
                                                          'availability': 'available'}, headers=self.staff)
        return r.json()['id']

    def reset(self):
        with db.transaction(self.conn):
            self.conn.execute('DELETE FROM production_progress')
            self.conn.execute('DELETE FROM production_jobs')

    def today(self):
        return today_local(self.tz)

    def new_job(self, *, status='order_confirmed', artisan_id=None, priority='normal', deadline=None):
        with db.transaction(self.conn):
            jid = repo.insert(self.conn, {'quantity': 1}, 'now')
            self.conn.execute('UPDATE production_jobs SET status = ?, artisan_id = ?, priority = ?, deadline = ? '
                              'WHERE id = ?', (status, artisan_id, priority, deadline, jid))
        return jid

    def close(self):
        self.conn.close()
        self.client_cm.__exit__(None, None, None)
        shutil.rmtree(self.dir, ignore_errors=True)


_ENV = None


def env() -> _Env:
    global _ENV
    if _ENV is None:
        _ENV = _Env()
        atexit.register(_ENV.close)
    return _ENV


def _job_row(e, jid):
    return e.conn.execute('SELECT * FROM production_jobs WHERE id = ?', (jid,)).fetchone()


# --- Req 24.9 -------------------------------------------------------------------------------------------------------

@hsettings(**PROFILE)
@given(specs=st.lists(st.tuples(STATUS, st.integers(min_value=-6, max_value=6)), min_size=1, max_size=8))
def test_overdue_iff_past_deadline_and_not_done(specs):
    e = env()
    e.reset()
    today = e.today()
    ids = [e.new_job(status=s, deadline=(today + timedelta(days=d)).isoformat()) for s, d in specs]
    listed = service.list_jobs(e.conn, tz=e.tz, status=None, artisan_id=None, priority=None, view='list',
                               limit=100, offset=0)
    flags = {j['id']: j['overdue'] for j in listed['items']}
    for jid, (status, offset) in zip(ids, specs):
        expected = offset < 0 and status not in ('completed', 'ready_for_fulfilment')
        assert flags[jid] is expected
        assert service.is_overdue(_job_row(e, jid), today) is expected


# --- Req 24.13 (filters) --------------------------------------------------------------------------------------------

@hsettings(**PROFILE)
@given(jobs=st.lists(st.tuples(STATUS, st.integers(min_value=0, max_value=2), PRIORITY), max_size=10),
       f_status=st.one_of(st.none(), STATUS), f_artisan=st.one_of(st.none(), st.integers(min_value=0, max_value=2)),
       f_priority=st.one_of(st.none(), PRIORITY), view=st.sampled_from(['list', 'board']))
def test_filters_return_exactly_matching_jobs(jobs, f_status, f_artisan, f_priority, view):
    e = env()
    e.reset()
    ids = [e.new_job(status=s, artisan_id=e.artisan_ids[a], priority=p) for s, a, p in jobs]
    artisan_filter = None if f_artisan is None else e.artisan_ids[f_artisan]
    expected = {jid for jid, (s, a, p) in zip(ids, jobs)
                if (f_status is None or s == f_status) and (f_artisan is None or a == f_artisan)
                and (f_priority is None or p == f_priority)}
    result = service.list_jobs(e.conn, tz=e.tz, status=f_status, artisan_id=artisan_filter, priority=f_priority,
                               view=view, limit=100, offset=0)
    if view == 'board':
        got = {j['id'] for col in result['columns'] for j in col['items']}
    else:
        got = {j['id'] for j in result['items']}
    assert got == expected
    assert result['total'] == len(expected)


# --- Req 24.6, 24.7 -------------------------------------------------------------------------------------------------

PERCENT = st.one_of(st.integers(min_value=-200, max_value=300), st.just(50.5), st.just('7'), st.just(None))
ACTOR = st.sampled_from(['staff', 'assigned', 'unassigned'])


@hsettings(**PROFILE)
@given(percent=PERCENT, actor=ACTOR)
def test_progress_accepted_iff_whole_0_100_from_staff_or_assigned(percent, actor):
    e = env()
    e.reset()
    jid = e.new_job(status='in_production', artisan_id=e.artisan_ids[0])
    headers = {'staff': e.staff, 'assigned': e.artisan_headers, 'unassigned': e.other_headers}[actor]
    r = e.client.post(f'/api/production/jobs/{jid}/progress', json={'percent': percent, 'note': 'n'}, headers=headers)
    valid = isinstance(percent, int) and 0 <= percent <= 100
    rows = e.conn.execute('SELECT percent FROM production_progress WHERE job_id = ?', (jid,)).fetchall()
    if actor == 'unassigned':
        # Body validation runs before the ownership check, so an invalid percent from an unassigned artisan is 422.
        assert r.status_code == (403 if valid else 422)
        assert rows == [] and _job_row(e, jid)['progress_percent'] == 0
    elif valid:
        assert r.status_code == 200
        assert [x['percent'] for x in rows] == [percent] and _job_row(e, jid)['progress_percent'] == percent
    else:
        assert r.status_code == 422
        assert rows == [] and _job_row(e, jid)['progress_percent'] == 0


# --- Req 24.3, 24.8 -------------------------------------------------------------------------------------------------

@hsettings(**PROFILE)
@given(offset=st.integers(min_value=-30, max_value=30), priority=PRIORITY, quantity=st.integers(1, 999999))
def test_deadlines_before_today_rejected(offset, priority, quantity):
    e = env()
    e.reset()
    jid = e.new_job()
    deadline = (e.today() + timedelta(days=offset)).isoformat()
    r = e.client.post(f'/api/production/jobs/{jid}/assign', headers=e.staff, json={
        'artisanId': e.artisan_ids[2], 'quantity': quantity, 'deadline': deadline, 'priority': priority})
    row = _job_row(e, jid)
    if offset < 0:
        assert r.status_code == 422
        assert 'deadline' in {d['field'] for d in r.json()['error']['details']}
        assert row['status'] == 'order_confirmed' and row['artisan_id'] is None and row['deadline'] is None
    else:
        assert r.status_code == 200
        assert (row['status'], row['artisan_id'], row['deadline'], row['priority'], row['quantity']) == (
            'production_assigned', e.artisan_ids[2], deadline, priority, quantity)


# --- Req 24.1 -------------------------------------------------------------------------------------------------------

LINES = st.lists(st.tuples(st.booleans(), st.integers(0, 6), st.integers(1, 6)), min_size=1, max_size=4)


@hsettings(**PROFILE)
@given(lines=LINES)
def test_confirming_order_creates_one_job_per_qualifying_line(lines):
    e = env()
    e.reset()
    pids = []
    for made_to_order, stock, _ in lines:
        r = e.client.post('/api/staff/products', headers=e.staff, json={
            'name': f'Item {next(_counter)}', 'categoryId': 1, 'priceSen': 1000, 'stock': stock,
            'madeToOrder': made_to_order})
        assert r.status_code == 201, r.text
        pids.append(r.json()['id'])
    with db.transaction(e.conn):
        order, _ = orders_api.create_order(e.conn, NewOrder(
            user_id=1, idempotency_key=f'k{next(_counter)}', customer_name='A B', email='a@x.com',
            phone='0123456789', delivery_address='1 Road', payment_method='card', payment_status='paid',
            shipping_fee_sen=800,
            lines=[NewOrderLine(product_id=pid, variation_id=None, sku_key=pid, name='Thing', unit_price_sen=1000,
                                quantity=qty) for pid, (_, _, qty) in zip(pids, lines)]))
    with db.transaction(e.conn):
        created = production_api.create_jobs_for_order(e.conn, order['id'])
        assert production_api.create_jobs_for_order(e.conn, order['id']) == []
    expected = {ln['id'] for ln, (mto, stock, qty) in zip(order['lines'], lines) if mto or qty > stock}
    rows = e.conn.execute('SELECT order_line_id, status FROM production_jobs WHERE order_id = ?',
                          (order['id'],)).fetchall()
    assert len(created) == len(expected) == len(rows)
    assert {r['order_line_id'] for r in rows} == expected
    assert all(r['status'] == 'order_confirmed' for r in rows)
