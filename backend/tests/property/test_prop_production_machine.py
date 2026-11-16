"""Property 26: Production status machine and independence.

For any pair of Production_Status values the transition is accepted if and only if it follows
order_confirmed->production_assigned->in_production->quality_checking->completed->ready_for_fulfilment or
quality_checking->in_production; and for any sequence of production and fulfilment changes, a change to one status
never alters the other, while reaching ready_for_fulfilment creates a staff notification and leaves the
Fulfilment_Status unchanged.

**Validates: Requirements 24.4, 24.5, 24.10, 24.11**
"""
from __future__ import annotations

import itertools
import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app

PASSWORD = ''.join(['Secret', '123'])
DELIVERY = {'name': 'Aisha Rahman', 'phone': '0123456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bunga, Taman Indah', 'postcode': '50450', 'state': 'Selangor'}
PROFILE = dict(max_examples=100, deadline=None, suppress_health_check=list(HealthCheck))
_counter = itertools.count()

STATUSES = ['order_confirmed', 'production_assigned', 'in_production', 'quality_checking', 'completed',
            'ready_for_fulfilment']
ALLOWED = {('order_confirmed', 'production_assigned'), ('production_assigned', 'in_production'),
           ('in_production', 'quality_checking'), ('quality_checking', 'completed'),
           ('quality_checking', 'in_production'), ('completed', 'ready_for_fulfilment')}
FULFIL_NEXT = {'placed': 'confirmed', 'confirmed': 'preparing', 'preparing': 'shipped', 'shipped': 'delivered'}


def _h(token):
    return {'Authorization': f'Bearer {token}'}


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='prod_sm_prop_'))
        self.settings = Settings(database_path=self.dir / 't.sqlite3', media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(self.settings))
        self.client = self.client_cm.__enter__()
        self.run(lambda c: [
            c.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, "
                      "created_at, updated_at) VALUES ('p1', 'Bag', '', 1, 1000, 1, 'now', 'now')"),
            c.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                      "VALUES ('p1', 'p1', NULL, 100000, 100000)")])
        self.customer = self._login('cust@example.com', 'Aisha')
        self._login('staff@example.com', 'Staff')
        self.run(lambda c: c.execute("UPDATE users SET role = 'seller' WHERE email = 'staff@example.com'"))
        self.staff = self.client.post('/api/auth/login', json={'email': 'staff@example.com',
                                                               'password': PASSWORD}).json()['token']
        self.staff_count = self.run(lambda c: c.execute(
            "SELECT COUNT(*) FROM users WHERE role IN ('seller','admin')").fetchone()[0])

    def _login(self, email, name):
        self.client.post('/api/auth/register', json={'name': name, 'email': email, 'password': PASSWORD})
        return self.client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']

    def run(self, fn):
        conn = db.connect(self.settings.database_path)
        try:
            with db.transaction(conn):
                return fn(conn)
        finally:
            conn.close()

    def new_order(self):
        assert self.client.post('/api/cart/lines', headers=_h(self.customer),
                                json={'productId': 'p1', 'quantity': 1}).status_code == 200
        r = self.client.post('/api/checkout', headers=_h(self.customer), json={
            'idempotencyKey': f'idem-{next(_counter):08d}', 'delivery': DELIVERY, 'method': 'cod'})
        assert r.status_code == 201, r.text
        return r.json()['id']

    def new_job(self, status, order_id=None):
        def make(c):
            cur = c.execute("INSERT INTO production_jobs (order_id, quantity, priority, status, progress_percent, "
                            "notes, is_demo, created_at, updated_at) VALUES (?, 1, 'normal', ?, 0, '', 0, 'now', 'now')",
                            (order_id, status))
            return cur.lastrowid
        return self.run(make)

    def job_status(self, job_id):
        return self.run(lambda c: c.execute('SELECT status FROM production_jobs WHERE id = ?',
                                            (job_id,)).fetchone()[0])

    def order_status(self, order_id):
        return self.run(lambda c: c.execute('SELECT status FROM orders WHERE id = ?', (order_id,)).fetchone()[0])

    def ready_notifications(self, job_id):
        return self.run(lambda c: c.execute(
            "SELECT COUNT(*) FROM notifications WHERE type = 'production' AND related_type = 'production_job' "
            "AND related_id = ?", (str(job_id),)).fetchone()[0])

    def close(self):
        self.client_cm.__exit__(None, None, None)
        shutil.rmtree(self.dir, ignore_errors=True)


_env: _Env | None = None


def _get_env() -> _Env:
    global _env
    if _env is None:
        _env = _Env()
    return _env


def teardown_module(_module):
    global _env
    if _env is not None:
        _env.close()
        _env = None


@hsettings(**PROFILE)
@given(st.sampled_from(STATUSES), st.sampled_from(STATUSES))
def test_production_transition_accepted_iff_in_sequence(current, requested):
    env = _get_env()
    job_id = env.new_job(current)
    resp = env.client.post(f'/api/production/jobs/{job_id}/status', headers=_h(env.staff),
                           json={'status': requested})
    notified = env.ready_notifications(job_id)
    if (current, requested) in ALLOWED:
        assert resp.status_code == 200, resp.text
        assert env.job_status(job_id) == requested
        # Req 24.10: a staff notification per Staff_User only on reaching ready_for_fulfilment.
        assert notified == (env.staff_count if requested == 'ready_for_fulfilment' else 0)
    else:
        # Req 24.5: 409 naming both statuses; status unchanged; no notification.
        assert resp.status_code == 409, resp.text
        assert current in resp.json()['error']['message'] and requested in resp.json()['error']['message']
        assert env.job_status(job_id) == current
        assert notified == 0


_ops = st.lists(st.tuples(st.sampled_from(['production', 'fulfilment']),
                          st.sampled_from(STATUSES + ['placed', 'confirmed', 'preparing', 'shipped', 'delivered'])),
                min_size=1, max_size=14)


@hsettings(**PROFILE)
@given(_ops)
def test_production_and_fulfilment_statuses_are_independent(ops):
    env = _get_env()
    order_id = env.new_order()
    job_id = env.new_job('order_confirmed', order_id)
    for kind, target in ops:
        job_before, order_before = env.job_status(job_id), env.order_status(order_id)
        notes_before = env.ready_notifications(job_id)
        if kind == 'production':
            resp = env.client.post(f'/api/production/jobs/{job_id}/status', headers=_h(env.staff),
                                   json={'status': target}) if target in STATUSES else None
            if resp is None:
                continue
            assert env.order_status(order_id) == order_before            # Req 24.4: production never moves fulfilment
            if resp.status_code == 200:
                assert env.job_status(job_id) == target
                if target == 'ready_for_fulfilment':                     # Req 24.10/24.11
                    assert env.ready_notifications(job_id) == notes_before + env.staff_count
            else:
                assert env.job_status(job_id) == job_before
        else:
            if target in STATUSES:
                continue
            resp = env.client.post(f'/api/staff/orders/{order_id}/status', headers=_h(env.staff),
                                   json={'status': target, 'shipping_reference': 'TRACK123'})
            assert env.job_status(job_id) == job_before                  # fulfilment never moves production
            assert env.ready_notifications(job_id) == notes_before
            if resp.status_code == 200:
                assert env.order_status(order_id) == target
            else:
                assert env.order_status(order_id) == order_before
