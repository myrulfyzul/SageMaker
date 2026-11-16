"""Property 22: Payment retry.

For any Order in `payment_failed` and any sequence of retries, each retry inserts a new Payment_Record and leaves
earlier records unchanged; a `success` retry marks the Order paid only if every line passes stock re-validation,
otherwise the Order stays `payment_failed` and the response lists the short items.

**Validates: Requirements 13.11, 13.12**
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
PRODUCTS = ('p1', 'p2')
_counter = itertools.count()

QUANTITIES = st.fixed_dictionaries({'p1': st.integers(1, 5), 'p2': st.integers(0, 5)})
# One retry: (outcome, stock for p1, stock for p2) set just before the retry.
RETRY = st.tuples(st.sampled_from(['success', 'failed']), st.integers(0, 8), st.integers(0, 8))
PROFILE = dict(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))


def _h(token):
    return {'Authorization': f'Bearer {token}'}


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='payment_retry_prop_'))
        self.settings = Settings(database_path=self.dir / 't.sqlite3', media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(self.settings))
        self.client = self.client_cm.__enter__()
        self.run(lambda c: [
            (c.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, "
                       "created_at, updated_at) VALUES (?, ?, '', 1, 1000, 1, 'now', 'now')", (p, f'Name {p}')),
             c.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                       "VALUES (?, ?, NULL, 0, 0)", (p, p))) for p in PRODUCTS])

    def run(self, fn):
        conn = db.connect(self.settings.database_path)
        try:
            with db.transaction(conn):
                return fn(conn)
        finally:
            conn.close()

    def set_stock(self, **levels):
        self.run(lambda c: [c.execute('UPDATE stock_levels SET quantity = ? WHERE sku_key = ?', (q, p))
                            for p, q in levels.items()])

    def stock(self, pid):
        return self.run(lambda c: c.execute('SELECT quantity FROM stock_levels WHERE sku_key = ?', (pid,))
                        .fetchone()[0])

    def payments(self, oid):
        return self.run(lambda c: [tuple(r) for r in c.execute(
            'SELECT * FROM payments WHERE order_id = ? ORDER BY id', (oid,)).fetchall()])

    def customer(self):
        email = f'u{next(_counter)}@example.com'
        self.client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
        return self.client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']

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
@given(QUANTITIES, st.lists(RETRY, min_size=1, max_size=6))
def test_payment_retry_appends_records_and_revalidates_stock(quantities, retries):
    env = _get_env()
    wanted = {p: q for p, q in quantities.items() if q > 0}
    env.set_stock(p1=50, p2=50)
    token = env.customer()
    for pid, qty in wanted.items():
        assert env.client.post('/api/cart/lines', headers=_h(token),
                               json={'productId': pid, 'quantity': qty}).status_code == 200
    r = env.client.post('/api/checkout', headers=_h(token), json={
        'idempotencyKey': f'idem-{next(_counter):08d}', 'delivery': DELIVERY, 'method': 'card', 'outcome': 'failed'})
    assert r.status_code == 201, r.text
    oid = r.json()['id']
    assert r.json()['status'] == 'payment_failed'
    assert env.stock('p1') == 50 and env.stock('p2') == 50  # failed payment restored stock

    url = f'/api/orders/{oid}/payments'
    paid = False
    for outcome, s1, s2 in retries:
        env.set_stock(p1=s1, p2=s2)
        before = env.payments(oid)
        resp = env.client.post(url, headers=_h(token), json={'method': 'card', 'outcome': outcome})
        after = env.payments(oid)

        if paid:  # an order that is no longer payment_failed cannot be retried
            assert resp.status_code == 409 and after == before
            continue

        short = {p: (q, s) for (p, q), s in zip(wanted.items(), [{'p1': s1, 'p2': s2}[p] for p in wanted])
                 if s < q}
        if outcome == 'failed':
            assert resp.status_code == 200 and resp.json()['status'] == 'payment_failed'
            assert len(after) == len(before) + 1
            assert env.stock('p1') == s1 and env.stock('p2') == s2
        elif short:
            assert resp.status_code == 409, resp.text
            error = resp.json()['error']
            assert error['code'] == 'insufficient_stock'
            assert {d['productId']: (d['requested'], d['available']) for d in error['details']} == short
            assert after == before  # nothing recorded, nothing deducted
            assert env.stock('p1') == s1 and env.stock('p2') == s2
            assert env.run(lambda c: c.execute('SELECT status FROM orders WHERE id = ?', (oid,)).fetchone()[0]) \
                == 'payment_failed'
        else:
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body['status'] == 'placed' and body['paymentStatus'] == 'paid'
            assert len(after) == len(before) + 1
            for pid in PRODUCTS:
                assert env.stock(pid) == {'p1': s1, 'p2': s2}[pid] - wanted.get(pid, 0)
            paid = True
        assert after[:len(before)] == before  # earlier Payment_Records are untouched
