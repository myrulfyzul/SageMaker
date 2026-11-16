"""Property 25: Order status state machine.

For any pair of (current status, requested status), including the legacy `packing` value read as `preparing`, the
transition is accepted if and only if it is placed->confirmed->preparing->shipped->delivered or a cancel from
placed, confirmed or preparing. A rejected transition returns 409 naming both statuses and changes no status,
history or stock. `shipped` requires a shipping reference of 3 to 80 characters and cancel a reason of 3 to 500.

**Validates: Requirements 22.5, 22.6, 22.7, 22.8, 22.9, 22.10, 22.11, 22.13**
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
PROFILE = dict(max_examples=120, deadline=None, suppress_health_check=list(HealthCheck))
_counter = itertools.count()

STORED = ['placed', 'confirmed', 'preparing', 'packing', 'shipped', 'delivered', 'cancelled', 'payment_failed']
TARGETS = ['placed', 'confirmed', 'preparing', 'shipped', 'delivered', 'cancelled', 'payment_failed']
NEXT = {'placed': 'confirmed', 'confirmed': 'preparing', 'preparing': 'shipped', 'shipped': 'delivered'}

_text = st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=0, max_size=600)
# Mix of clearly valid, boundary and invalid lengths; ordinary text so strip() never changes the length.
REF = st.one_of(st.none(), _text.map(lambda s: s[:90]), st.integers(0, 90).map(lambda n: 'r' * n))
REASON = st.one_of(st.none(), _text, st.integers(0, 520).map(lambda n: 'c' * n))


def _h(token):
    return {'Authorization': f'Bearer {token}'}


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='order_sm_prop_'))
        self.settings = Settings(database_path=self.dir / 't.sqlite3', media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(self.settings))
        self.client = self.client_cm.__enter__()
        self.run(lambda c: [
            c.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, "
                      "created_at, updated_at) VALUES ('p1', 'Bag', '', 1, 1000, 1, 'now', 'now')"),
            c.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                      "VALUES ('p1', 'p1', NULL, 100000, 100000)")])
        self.customer = self.login('cust@example.com')
        self.client.post('/api/auth/register', json={'name': 'Staff', 'email': 'staff@example.com',
                                                     'password': PASSWORD})
        self.run(lambda c: c.execute("UPDATE users SET role = 'seller' WHERE email = 'staff@example.com'"))
        self.staff = self.client.post('/api/auth/login', json={'email': 'staff@example.com',
                                                               'password': PASSWORD}).json()['token']

    def login(self, email):
        self.client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
        return self.client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']

    def run(self, fn):
        conn = db.connect(self.settings.database_path)
        try:
            with db.transaction(conn):
                return fn(conn)
        finally:
            conn.close()

    def new_order(self, stored_status):
        assert self.client.post('/api/cart/lines', headers=_h(self.customer),
                                json={'productId': 'p1', 'quantity': 2}).status_code == 200
        r = self.client.post('/api/checkout', headers=_h(self.customer), json={
            'idempotencyKey': f'idem-{next(_counter):08d}', 'delivery': DELIVERY, 'method': 'cod'})
        assert r.status_code == 201, r.text
        oid = r.json()['id']
        self.run(lambda c: c.execute('UPDATE orders SET status = ? WHERE id = ?', (stored_status, oid)))
        return oid

    def snapshot(self, oid):
        def read(c):
            order = tuple(c.execute('SELECT status, shipping_reference, cancel_reason, stock_restored, updated_at '
                                    'FROM orders WHERE id = ?', (oid,)).fetchone())
            history = c.execute('SELECT COUNT(*) FROM order_history WHERE order_id = ?', (oid,)).fetchone()[0]
            stock = c.execute("SELECT quantity FROM stock_levels WHERE sku_key = 'p1'").fetchone()[0]
            return order, history, stock
        return self.run(read)

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
@given(st.sampled_from(STORED), st.sampled_from(TARGETS), REF, REASON)
def test_order_status_transitions_follow_state_machine(stored, target, ref, reason):
    env = _get_env()
    oid = env.new_order(stored)
    current = 'preparing' if stored == 'packing' else stored  # Req 22.13
    before = env.snapshot(oid)

    body = {'status': target}
    if ref is not None:
        body['shipping_reference'] = ref
    if reason is not None:
        body['reason'] = reason
    resp = env.client.post(f'/api/staff/orders/{oid}/status', headers=_h(env.staff), json=body)
    after = env.snapshot(oid)

    allowed = NEXT.get(current) == target or (target == 'cancelled' and current in ('placed', 'confirmed', 'preparing'))
    if not allowed:
        # Req 22.8 to 22.10: 409 naming both statuses; no status, history or stock change.
        assert resp.status_code == 409, resp.text
        error = resp.json()['error']
        assert error['code'] == 'invalid_transition'
        assert current in error['message'] and target in error['message']
        assert after == before
        return

    ref_ok = ref is not None and 3 <= len(ref.strip()) <= 80
    reason_ok = reason is not None and 3 <= len(reason.strip()) <= 500
    if (target == 'shipped' and not ref_ok) or (target == 'cancelled' and not reason_ok):
        # Req 22.6, 22.7: field validation failure, nothing changed.
        assert resp.status_code == 422, resp.text
        assert after == before
        return

    assert resp.status_code == 200, resp.text
    assert resp.json()['status'] == target
    assert after[0][0] == target
    assert after[1] == before[1] + 1                       # exactly one history row (Req 22.11)
    if target == 'shipped':
        assert after[0][1] == ref.strip()
    if target == 'cancelled':
        assert after[0][2] == reason.strip()
        assert after[2] == before[2] + 2                   # stock of the 2 units restored once
    else:
        assert after[2] == before[2]
