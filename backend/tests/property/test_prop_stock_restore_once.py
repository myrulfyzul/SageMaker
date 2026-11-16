"""Property 23: Stock restoration happens exactly once.

**Validates: Requirements 14.9, 14.10, 22.11**

For any order with any line quantities, moving it to `cancelled` or `payment_failed` restores each line quantity to
stock and records one restoring Stock_Adjustment per line. Any number of further restore attempts or further moves
into those states (repeat restores, failed payment retries) leave stock and the adjustment ledger unchanged.
"""
from __future__ import annotations

import itertools
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app
from app.modules.checkout import service as checkout_service
from app.modules.checkout.schemas import CheckoutIn
from app.modules.inventory import api as inventory_api
from app.modules.orders import service as orders_service
from app.modules.orders.schemas import StatusChange
from app.modules.payments.schemas import PaymentRequest

PASSWORD = ''.join(['Secret', '123'])
PROFILE = dict(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
_counter = itertools.count()

DELIVERY = {'name': 'Aisha Rahman', 'phone': '012-3456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bukit Bintang', 'postcode': '50200', 'state': 'Kuala Lumpur'}

QUANTITIES = st.lists(st.integers(min_value=1, max_value=5), min_size=1, max_size=4)
# How the order reaches a restoring state.
ROUTE = st.sampled_from(['payment_failed', 'payment_cancelled', 'staff_cancel'])
EXTRA_RESTORES = st.integers(min_value=1, max_value=4)
EXTRA_RETRIES = st.integers(min_value=0, max_value=2)


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='restore_prop_'))
        self.settings = Settings(database_path=self.dir / 't.sqlite3', media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(self.settings))
        self.client = self.client_cm.__enter__()
        self.conn = db.connect(self.settings.database_path)

    def make_products(self, quantities, stock):
        pids = []
        with db.transaction(self.conn):
            for _ in quantities:
                pid = f'p{next(_counter)}'
                pids.append(pid)
                self.conn.execute(
                    "INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                    "updated_at) VALUES (?, ?, '', 1, 1000, 1, 'now', 'now')", (pid, pid))
                self.conn.execute(
                    'INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) '
                    'VALUES (?, ?, NULL, ?, ?)', (pid, pid, stock, stock))
        return pids

    def customer_with_lines(self, pids, quantities):
        email = f'u{next(_counter)}@example.com'
        self.client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
        token = self.client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
        for pid, qty in zip(pids, quantities):
            r = self.client.post('/api/cart/lines', headers={'Authorization': f'Bearer {token}'},
                                 json={'productId': pid, 'quantity': qty})
            assert r.status_code == 200, r.text
        return self.conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()['id']

    def stock(self, pids):
        return {p: self.conn.execute('SELECT quantity FROM stock_levels WHERE sku_key = ?', (p,)).fetchone()[0]
                for p in pids}

    def ledger(self, order_id):
        rows = self.conn.execute(
            'SELECT sku_key, delta FROM stock_adjustments WHERE order_id = ? ORDER BY id', (order_id,)).fetchall()
        return [(r['sku_key'], r['delta']) for r in rows]

    def close(self):
        self.conn.close()
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
@given(QUANTITIES, ROUTE, EXTRA_RESTORES, EXTRA_RETRIES)
def test_stock_restored_exactly_once(quantities, route, extra_restores, extra_retries):
    env = _get_env()
    initial = 50
    pids = env.make_products(quantities, initial)
    uid = env.customer_with_lines(pids, quantities)

    method, outcome = {'payment_failed': ('card', 'failed'), 'payment_cancelled': ('fpx', 'cancelled'),
                       'staff_cancel': ('card', 'success')}[route]
    body = CheckoutIn(idempotency_key=f'key-{uid}-{next(_counter)}-abcdef', delivery=DELIVERY, method=method,
                      outcome=outcome)
    order, created = checkout_service.place_order(env.conn, uid, body)
    assert created is True
    order_id = order['id']

    if route == 'staff_cancel':
        # Stock is held until the staff cancel.
        assert env.stock(pids) == {p: initial - q for p, q in zip(pids, quantities)}
        orders_service.change_status(env.conn, order_id, StatusChange(status='cancelled', reason='Customer asked'), uid)

    # Req 14.9: every line quantity is back, one restoring adjustment per line.
    assert env.stock(pids) == {p: initial for p in pids}
    ledger = env.ledger(order_id)
    restoring = [(sku, d) for sku, d in ledger if d > 0]
    assert sorted(restoring) == sorted(zip(pids, quantities))
    assert len(restoring) == len(quantities)

    stock_after, ledger_after = env.stock(pids), ledger

    # Req 14.10: further moves into restoring states change nothing.
    for _ in range(extra_restores):
        with db.transaction(env.conn):
            assert inventory_api.restore_for_order(env.conn, order_id) is False
    if route == 'payment_failed':
        # Failed retries re-enter payment_failed without reserving or restoring anything.
        for _ in range(extra_retries):
            orders_service.retry_payment(env.conn, uid, order_id, PaymentRequest(method='card', outcome='failed'))
    else:
        # A cancelled order cannot be cancelled or retried again.
        with pytest.raises(orders_service.InvalidTransition):
            orders_service.change_status(env.conn, order_id,
                                         StatusChange(status='cancelled', reason='Again please'), uid)
        with pytest.raises(orders_service.InvalidTransition):
            orders_service.retry_payment(env.conn, uid, order_id, PaymentRequest(method='card', outcome='failed'))

    assert env.stock(pids) == stock_after
    assert env.ledger(order_id) == ledger_after
