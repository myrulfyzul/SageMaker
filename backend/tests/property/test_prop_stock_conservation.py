"""Property 19: Stock conservation under checkout, including concurrency.

**Validates: Requirements 14.3, 14.4, 14.5**

Customers each hold one line for the same product, then check out at the same moment from separate threads, each with
its own connection to the same database file. Final stock must equal initial stock minus the units of orders that did
not restore their stock, never go negative, and every rejection must be a 409 that lists the short product and
leaves no order behind.
"""
from __future__ import annotations

import itertools
import shutil
import tempfile
import threading
from pathlib import Path

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app
from app.modules.checkout import service
from app.modules.checkout.schemas import CheckoutIn
from app.modules.inventory.api import InsufficientStock

PASSWORD = ''.join(['Secret', '123'])
PROFILE = dict(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
_counter = itertools.count()

DELIVERY = {'name': 'Aisha Rahman', 'phone': '012-3456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bukit Bintang', 'postcode': '50200', 'state': 'Kuala Lumpur'}

BUYER = st.fixed_dictionaries({
    'quantity': st.integers(min_value=1, max_value=5),
    'method_outcome': st.sampled_from([('card', 'success'), ('cod', None), ('card', 'failed'),
                                       ('fpx', 'cancelled'), ('ewallet', 'success')]),
})
SCENARIO = st.tuples(st.integers(min_value=5, max_value=20), st.lists(BUYER, min_size=2, max_size=8))


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='stock_prop_'))
        self.settings = Settings(database_path=self.dir / 't.sqlite3', media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(self.settings))
        self.client = self.client_cm.__enter__()

    def connect(self):
        return db.connect(self.settings.database_path)

    def make_product(self, pid, stock):
        conn = self.connect()
        try:
            with db.transaction(conn):
                conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, "
                             "created_at, updated_at) VALUES (?, ?, '', 1, 1000, 1, 'now', 'now')", (pid, pid))
                conn.execute('INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) '
                             'VALUES (?, ?, NULL, ?, ?)', (pid, pid, stock, stock))
        finally:
            conn.close()

    def customer_with_line(self, pid, quantity):
        email = f'u{next(_counter)}@example.com'
        self.client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
        token = self.client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
        r = self.client.post('/api/cart/lines', headers={'Authorization': f'Bearer {token}'},
                             json={'productId': pid, 'quantity': quantity})
        assert r.status_code == 200, r.text
        conn = self.connect()
        try:
            return conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()['id']
        finally:
            conn.close()

    def scalar(self, sql, params=()):
        conn = self.connect()
        try:
            return conn.execute(sql, params).fetchone()[0]
        finally:
            conn.close()

    def close(self):
        self.client_cm.__exit__(None, None, None)
        shutil.rmtree(self.dir, ignore_errors=True)


_env = None


def _get_env():
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
@given(SCENARIO)
def test_stock_conserved_under_concurrent_checkout(scenario):
    stock, buyers = scenario
    env = _get_env()
    pid = f'p{next(_counter)}'
    env.make_product(pid, stock)
    user_ids = [env.customer_with_line(pid, b['quantity']) for b in buyers]

    barrier = threading.Barrier(len(buyers))
    results = [None] * len(buyers)

    def worker(i):
        method, outcome = buyers[i]['method_outcome']
        body = CheckoutIn(idempotency_key=f'key-{pid}-{i}-abcdef', delivery=DELIVERY, method=method, outcome=outcome)
        conn = env.connect()
        try:
            barrier.wait(timeout=30)
            order, created = service.place_order(conn, user_ids[i], body)
            results[i] = ('ok', order, created)
        except InsufficientStock as exc:
            results[i] = ('short', exc, None)
        except BaseException as exc:  # surfaced by the assertions below
            results[i] = ('error', exc, None)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(buyers))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    accepted_units = 0
    accepted_orders = 0
    for i, (kind, value, created) in enumerate(results):
        assert kind in ('ok', 'short'), f'unexpected result {kind}: {value!r}'
        if kind == 'ok':
            assert created is True
            accepted_orders += 1
        else:
            # Req 14.3: 409 listing each short product with its available quantity; nothing was written.
            assert value.status == 409
            assert [d['productId'] for d in value.details] == [pid]
            detail = value.details[0]
            assert detail['requested'] == buyers[i]['quantity']
            assert 0 <= detail['available'] < detail['requested']

    final = env.scalar('SELECT quantity FROM stock_levels WHERE sku_key = ?', (pid,))
    held = env.scalar(
        'SELECT COALESCE(SUM(l.quantity), 0) FROM order_lines l JOIN orders o ON o.id = l.order_id '
        'WHERE l.product_id = ? AND o.stock_restored = 0', (pid,)) or 0
    order_count = env.scalar('SELECT COUNT(DISTINCT order_id) FROM order_lines WHERE product_id = ?', (pid,))

    assert final >= 0                                    # Req 14.4: never oversold
    assert final == stock - held                         # Req 14.5: conservation
    assert held <= stock
    assert order_count == accepted_orders                # rejected checkouts created no order
    # Ledger agrees with the stock row.
    assert env.scalar('SELECT COALESCE(SUM(delta), 0) FROM stock_adjustments WHERE product_id = ?', (pid,)) == final - stock
    # Rejected customers keep their cart; accepted ones have it cleared.
    for uid, (kind, _v, _c) in zip(user_ids, results):
        remaining = env.scalar('SELECT COUNT(*) FROM cart_lines WHERE user_id = ?', (uid,))
        assert remaining == (0 if kind == 'ok' else 1)
