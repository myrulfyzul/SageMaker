"""Property 27 (Custom order state machine) and Property 28 (custom order part).

27: for any pair of Custom_Order_Status values a transition is accepted iff it is submitted->accepted,
submitted->rejected, accepted->in_progress or in_progress->completed; every other pair returns 409 and leaves the status
unchanged; accept needs an integer price 1..99,999,999 and reject a reason of 5..500 characters after trimming.

28: each operation that really changes the status creates exactly one Notification for the owner; an operation that
does not change the status (same status, illegal pair, invalid payload) creates none.

**Validates: Requirements 17.3, 25.3, 25.4, 25.5, 25.6, 25.10**
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
STATUSES = ['submitted', 'accepted', 'rejected', 'in_progress', 'completed']
ALLOWED = {('submitted', 'accepted'), ('submitted', 'rejected'), ('accepted', 'in_progress'),
           ('in_progress', 'completed')}


def _h(token):
    return {'Authorization': f'Bearer {token}'}


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='coprop_'))
        self.db_path = self.dir / 't.sqlite3'
        settings = Settings(database_path=self.db_path, media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(settings))
        self.client = self.client_cm.__enter__()
        self.staff_token = self._user('staff-co@example.com', 'seller')[1]
        self.owner_id, _ = self._user('owner-co@example.com')

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
        return self.sql('SELECT id FROM users WHERE email = ?', (email,))[0][0], token

    def new_custom_order(self):
        self.sql("INSERT INTO custom_orders (user_id, product_type, description, quantity, preferred_date, status, "
                 "created_at, updated_at) VALUES (?, 'Vase', 'A hand made ceramic vase', 1, '2099-01-01', "
                 "'submitted', 'now', 'now')", (self.owner_id,))
        return self.sql('SELECT max(id) FROM custom_orders')[0][0]

    def status(self, co_id):
        return self.sql('SELECT status FROM custom_orders WHERE id = ?', (co_id,))[0][0]

    def notes(self, co_id):
        return self.sql("SELECT id, user_id FROM notifications WHERE type = 'custom_order' AND "
                        "title = 'Custom order update' AND related_type = 'custom_order' AND related_id = ? "
                        "ORDER BY id", (str(co_id),))

    def post(self, co_id, action, body):
        return self.client.post(f'/api/staff/custom-orders/{co_id}/{action}', headers=_h(self.staff_token), json=body)

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


prices = st.one_of(st.sampled_from([0, 1, 99_999_999, 100_000_000, -1, 1.5, '1000', None]),
                   st.integers(-10, 150_000_000))
reasons = st.one_of(st.sampled_from(['', '    ', ' abcd ', ' abcde ', 'a' * 500, 'a' * 501, ' ' + 'a' * 500 + ' ']),
                    st.text(alphabet='abc  ', min_size=0, max_size=12))
ops = st.one_of(
    st.tuples(st.just('accept'), prices),
    st.tuples(st.just('reject'), reasons),
    st.tuples(st.just('status'), st.sampled_from(STATUSES + ['bogus'])))


def _price_ok(p):
    return isinstance(p, int) and not isinstance(p, bool) and 1 <= p <= 99_999_999


def _reason_ok(r):
    return 5 <= len(r.strip()) <= 500


@hsettings(**PROFILE)
@given(st.lists(ops, min_size=1, max_size=14))
def test_custom_order_machine_and_notifications(operations):
    env = _get_env()
    co_id = env.new_custom_order()
    current = 'submitted'
    for kind, arg in operations:
        notes_before = env.notes(co_id)
        if kind == 'accept':
            target, valid = 'accepted', _price_ok(arg)
            r = env.post(co_id, 'accept', {'estimatedPriceSen': arg})
        elif kind == 'reject':
            target, valid = 'rejected', _reason_ok(arg)
            r = env.post(co_id, 'reject', {'reason': arg})
        else:
            target, valid = arg, arg in STATUSES and arg not in ('accepted', 'rejected')
            r = env.post(co_id, 'status', {'status': arg})
        legal = (current, target) in ALLOWED
        if kind == 'status' and target not in STATUSES:
            assert r.status_code == 422, r.text
            changed = False
        elif kind != 'status' and not valid:
            assert r.status_code == 422, r.text  # payload validated before the transition check
            changed = False
        elif not legal:
            assert r.status_code == 409, r.text
            changed = False
        elif kind == 'status' and not valid:
            assert r.status_code == 422, r.text  # accepted/rejected must use their own endpoints
            changed = False
        else:
            assert r.status_code == 200, r.text
            assert r.json()['status'] == target
            changed = True
        notes_after = env.notes(co_id)
        if changed:
            assert notes_after[:len(notes_before)] == notes_before
            assert len(notes_after) == len(notes_before) + 1
            assert notes_after[-1][1] == env.owner_id
            current = target
        else:
            assert notes_after == notes_before
        assert env.status(co_id) == current
