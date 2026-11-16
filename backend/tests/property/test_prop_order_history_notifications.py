"""Property 28 (orders part): One history row and one notification per real status change.

For any sequence of status-set operations on an Order, each operation that changes the status appends exactly one
history entry (previous status, new status, actor, time) and creates exactly one Notification for the owner; an
operation that sets the status to its current value (or is otherwise rejected) creates neither.

**Validates: Requirements 15.5, 17.2, 17.4, 22.12**
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
_counter = itertools.count()
PROFILE = dict(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))
STATUSES = ['placed', 'confirmed', 'preparing', 'shipped', 'delivered', 'cancelled', 'payment_failed']
NEXT = {'placed': 'confirmed', 'confirmed': 'preparing', 'preparing': 'shipped', 'shipped': 'delivered'}
CANCELLABLE = ('placed', 'confirmed', 'preparing')
DELIVERY = {'name': 'Aisha Rahman', 'phone': '0123456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bukit Bintang', 'postcode': '55100', 'state': 'Kuala Lumpur'}


def _h(token):
    return {'Authorization': f'Bearer {token}'}


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='histprop_'))
        self.db_path = self.dir / 't.sqlite3'
        settings = Settings(database_path=self.db_path, media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(settings))
        self.client = self.client_cm.__enter__()
        self.staff_id, self.staff_token = self._user('staff-hist@example.com', 'seller')
        self.sql("DELETE FROM products WHERE id = 'hp1'")
        self.sql("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                 "updated_at) VALUES ('hp1', 'Hist Product', '', 1, 1000, 1, 'now', 'now')")
        self.sql('INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) '
                 "VALUES ('hp1', 'hp1', NULL, 1000000, 1000000)")

    def sql(self, query, params=()):
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                return conn.execute(query, params).fetchall()
        finally:
            conn.close()

    def _user(self, email, role='customer'):
        self.client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
        if role != 'customer':
            self.sql('UPDATE users SET role = ? WHERE email = ?', (role, email))
        token = self.client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
        uid = self.sql('SELECT id FROM users WHERE email = ?', (email,))[0][0]
        return uid, token

    def new_order(self):
        """A fresh customer with one `placed` order. Returns (customer id, order id)."""
        uid, token = self._user(f'h{next(_counter)}@example.com')
        r = self.client.post('/api/cart/lines', headers=_h(token), json={'productId': 'hp1', 'quantity': 1})
        assert r.status_code == 200, r.text
        r = self.client.post('/api/checkout', headers=_h(token), json={
            'idempotencyKey': f'idem-key-{next(_counter):08d}', 'delivery': DELIVERY, 'method': 'card',
            'outcome': 'success'})
        assert r.status_code == 201, r.text
        return uid, r.json()['id']

    def history(self, order_id):
        return self.sql('SELECT id, previous_status, new_status, actor_user_id, created_at FROM order_history '
                        'WHERE order_id = ? ORDER BY id', (order_id,))

    def notifications(self, user_id, order_id):
        return self.sql("SELECT id FROM notifications WHERE user_id = ? AND type = 'order' "
                        "AND related_type = 'order' AND related_id = ? AND title = 'Order update' ORDER BY id",
                        (user_id, order_id))

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
@given(st.lists(st.sampled_from(STATUSES), min_size=1, max_size=12))
def test_one_history_row_and_one_notification_per_real_change(targets):
    env = _get_env()
    owner, order_id = env.new_order()
    current = 'placed'
    assert len(env.history(order_id)) == 1  # the creation row
    for target in targets:
        hist_before = env.history(order_id)
        notes_before = env.notifications(owner, order_id)
        body = {'status': target, 'shipping_reference': 'TRACK-12345', 'reason': 'customer asked to cancel'}
        r = env.client.post(f'/api/staff/orders/{order_id}/status', headers=_h(env.staff_token), json=body)
        hist_after = env.history(order_id)
        notes_after = env.notifications(owner, order_id)
        legal = NEXT.get(current) == target or (target == 'cancelled' and current in CANCELLABLE)
        if legal:
            assert r.status_code == 200, r.text
            assert r.json()['status'] == target
            # Exactly one new immutable history row; earlier rows untouched.
            assert hist_after[:len(hist_before)] == hist_before
            assert len(hist_after) == len(hist_before) + 1
            _id, prev, new, actor, at = hist_after[-1]
            assert (prev, new, actor) == (current, target, env.staff_id) and at
            # Exactly one new notification for the owner.
            assert notes_after[:len(notes_before)] == notes_before
            assert len(notes_after) == len(notes_before) + 1
            current = target
        else:
            # Same-status (and any other rejected) operations leave no trace.
            assert r.status_code == 409, r.text
            assert hist_after == hist_before
            assert notes_after == notes_before
    assert env.sql('SELECT status FROM orders WHERE id = ?', (order_id,))[0][0] == current


@hsettings(**PROFILE)
@given(st.sampled_from(STATUSES))
def test_setting_current_status_is_a_noop(target):
    """Setting an order to the status it already holds never writes history or notifications."""
    env = _get_env()
    owner, order_id = env.new_order()
    # Walk to `target` where reachable, then repeat it.
    path = {'placed': [], 'confirmed': ['confirmed'], 'preparing': ['confirmed', 'preparing'],
            'shipped': ['confirmed', 'preparing', 'shipped'],
            'delivered': ['confirmed', 'preparing', 'shipped', 'delivered'], 'cancelled': ['cancelled'],
            'payment_failed': None}[target]
    if path is None:
        return
    for step in path:
        r = env.client.post(f'/api/staff/orders/{order_id}/status', headers=_h(env.staff_token),
                            json={'status': step, 'shipping_reference': 'TRACK-12345', 'reason': 'changed my mind'})
        assert r.status_code == 200, r.text
    hist, notes = env.history(order_id), env.notifications(owner, order_id)
    assert len(hist) == 1 + len(path) and len(notes) == len(path)
    r = env.client.post(f'/api/staff/orders/{order_id}/status', headers=_h(env.staff_token),
                        json={'status': target, 'shipping_reference': 'TRACK-12345', 'reason': 'changed my mind'})
    assert r.status_code == 409
    assert env.history(order_id) == hist and env.notifications(owner, order_id) == notes
