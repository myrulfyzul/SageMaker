"""Property 24: Stock ledger invariant.

**Validates: Requirements 14.9, 21.1, 21.2, 21.3, 21.5, 21.8**

For any sequence of staff adjustments, checkouts (including payment outcomes that restore stock at once) and staff
cancellations on one stock holder: current stock equals opening stock plus the sum of all ledger deltas; an adjustment
(or checkout) that would make stock negative is rejected with 409 and writes nothing; and the low-stock flag is true
if and only if stock is at or below the current threshold.
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
from app.modules.checkout import service as checkout_service
from app.modules.checkout.schemas import CheckoutIn
from app.modules.inventory import api as inventory_api
from app.modules.inventory import service as inventory_service
from app.modules.inventory.api import InsufficientStock
from app.modules.orders import service as orders_service
from app.modules.orders.schemas import StatusChange

PASSWORD = ''.join(['Secret', '123'])
PROFILE = dict(max_examples=25, deadline=None, suppress_health_check=list(HealthCheck))
_counter = itertools.count()

DELIVERY = {'name': 'Aisha Rahman', 'phone': '012-3456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bukit Bintang', 'postcode': '50200', 'state': 'Kuala Lumpur'}

OUTCOMES = [('card', 'success'), ('cod', None), ('card', 'failed'), ('fpx', 'cancelled')]

OPERATION = st.one_of(
    st.tuples(st.just('adjust'), st.integers(min_value=-30, max_value=30).filter(lambda d: d != 0)),
    st.tuples(st.just('checkout'), st.integers(min_value=1, max_value=8), st.sampled_from(OUTCOMES)),
    st.tuples(st.just('cancel'), st.integers(min_value=0, max_value=10)),
    st.tuples(st.just('threshold'), st.integers(min_value=0, max_value=40)),
)
SCENARIO = st.tuples(st.integers(min_value=0, max_value=30), st.lists(OPERATION, min_size=1, max_size=12))


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='ledger_prop_'))
        self.settings = Settings(database_path=self.dir / 't.sqlite3', media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(self.settings))
        self.client = self.client_cm.__enter__()
        self.conn = db.connect(self.settings.database_path)

    def make_product(self, pid, stock):
        with db.transaction(self.conn):
            self.conn.execute(
                "INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                "updated_at) VALUES (?, ?, '', 1, 1000, 1, 'now', 'now')", (pid, pid))
            inventory_api.initialise(self.conn, pid, None, stock)

    def customer_with_line(self, pid, quantity):
        email = f'u{next(_counter)}@example.com'
        self.client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
        uid = self.conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()['id']
        # Written directly: the cart API refuses lines above current stock, but stock can fall after a line is added.
        with db.transaction(self.conn):
            self.conn.execute(
                "INSERT INTO cart_lines (user_id, product_id, variation_id, sku_key, quantity, created_at, updated_at) "
                "VALUES (?, ?, NULL, ?, ?, 'now', 'now')", (uid, pid, pid, quantity))
        return uid

    def scalar(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()[0]

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
@given(SCENARIO)
def test_stock_ledger_invariant(scenario):
    opening, operations = scenario
    env = _get_env()
    pid = f'p{next(_counter)}'
    env.make_product(pid, opening)
    staff_id = env.customer_with_line(pid, 1)  # doubles as the acting user for cancellations

    expected = opening
    threshold = inventory_api.repo.DEFAULT_LOW_STOCK_THRESHOLD
    held_orders = []  # (order_id, owner_id, quantity) whose stock is still reserved

    def ledger_state():
        return (env.scalar('SELECT COUNT(*) FROM stock_adjustments WHERE product_id = ?', (pid,)),
                env.scalar('SELECT quantity FROM stock_levels WHERE sku_key = ?', (pid,)))

    for op in operations:
        before = ledger_state()
        kind = op[0]
        if kind == 'adjust':
            delta = op[1]
            if expected + delta < 0:
                try:
                    inventory_service.adjust(env.conn, pid, None, delta, 'Count correction', staff_id)
                    raise AssertionError('negative adjustment was accepted')
                except InsufficientStock as exc:
                    assert exc.status == 409
                assert ledger_state() == before            # Req 21.3: no write at all
            else:
                inventory_service.adjust(env.conn, pid, None, delta, 'Count correction', staff_id)
                expected += delta
        elif kind == 'threshold':
            inventory_service.set_threshold(env.conn, pid, op[1])
            threshold = op[1]
        elif kind == 'checkout':
            qty, (method, outcome) = op[1], op[2]
            uid = env.customer_with_line(pid, qty)
            body = CheckoutIn(idempotency_key=f'key-{pid}-{next(_counter)}-abcdef', delivery=DELIVERY,
                              method=method, outcome=outcome)
            if qty > expected:
                try:
                    checkout_service.place_order(env.conn, uid, body)
                    raise AssertionError('oversell was accepted')
                except InsufficientStock as exc:
                    assert exc.status == 409
                assert ledger_state() == before
            else:
                order, created = checkout_service.place_order(env.conn, uid, body)
                assert created is True
                if outcome in ('failed', 'cancelled'):
                    pass  # reserved then restored at once (Req 14.9): net zero
                else:
                    expected -= qty
                    held_orders.append((order['id'], uid, qty))
        else:  # cancel
            if held_orders:
                order_id, uid, qty = held_orders.pop(op[1] % len(held_orders))
                orders_service.change_status(env.conn, order_id, StatusChange(status='cancelled', reason='Customer asked'),
                                             staff_id)
                expected += qty

        # Invariants after every step.
        stock = env.scalar('SELECT quantity FROM stock_levels WHERE sku_key = ?', (pid,))
        ledger_sum = env.scalar('SELECT COALESCE(SUM(delta), 0) FROM stock_adjustments WHERE product_id = ?', (pid,))
        opening_row = env.scalar('SELECT opening_quantity FROM stock_levels WHERE sku_key = ?', (pid,))
        assert stock >= 0
        assert opening_row == opening
        assert stock == opening_row + ledger_sum           # Req 21.1, 21.5
        assert stock == expected                           # model agrees (Req 14.9)
        level = inventory_api.get_level(env.conn, pid)
        assert level['quantity'] == stock
        assert level['lowStockThreshold'] == threshold
        assert level['lowStock'] is (stock <= threshold)   # Req 21.8
