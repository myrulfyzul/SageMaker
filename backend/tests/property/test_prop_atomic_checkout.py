"""Property 50: Atomic order creation (checkout part).

A single failure injected at any step of checkout (after that step's own writes have been made) leaves no order,
order line, payment record, stock deduction, stock adjustment, notification or cart change behind.

**Validates: Requirements 14.2**
"""
from __future__ import annotations

import itertools
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app
from app.modules.checkout import service
from app.modules.checkout.schemas import CheckoutIn

PASSWORD = ''.join(['Secret', '123'])
DELIVERY = {'name': 'Aisha Rahman', 'phone': '0123456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bunga, Taman Indah', 'postcode': '50450', 'state': 'Selangor'}
_counter = itertools.count()
PROFILE = dict(max_examples=30, deadline=None, suppress_health_check=list(HealthCheck))

# step name -> (module object, attribute name) whose real effect is performed and then made to fail
STEPS = {
    'reserve': (service.inventory_api, 'reserve_for_order'),
    'order_create': (service.orders_api, 'create_order'),
    'payment_record': (service.payments_api, 'record'),
    'cart_clear': (service.cart_api, 'clear'),
    'notifications': (service.notifications_api, 'order_created'),
}
# restore_for_order only runs for failed/cancelled outcomes; it is a further step worth failing too.
RESTORE_STEP = (service.inventory_api, 'restore_for_order')

TABLES = ['orders', 'order_lines', 'order_history', 'payments', 'stock_adjustments', 'notifications', 'cart_lines']

step_st = st.sampled_from(sorted(STEPS))
qty_st = st.integers(min_value=1, max_value=5)
method_outcome_st = st.sampled_from([('card', 'success'), ('fpx', 'failed'), ('ewallet', 'cancelled'),
                                     ('cod', None)])


class Injected(RuntimeError):
    pass


@pytest.fixture(scope='module')
def env():
    d = Path(tempfile.mkdtemp(prefix='atomic_checkout_'))
    settings = Settings(database_path=d / 't.sqlite3', media_dir=d / 'media', demo_mode=True)
    cm = TestClient(create_app(settings))
    client = cm.__enter__()
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                     "updated_at) VALUES ('p1', 'Bag', '', 1, 1000, 1, 'now', 'now')")
        conn.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                     "VALUES ('p1', 'p1', NULL, 100000, 100000)")
    conn.close()
    yield client, settings
    cm.__exit__(None, None, None)
    shutil.rmtree(d, ignore_errors=True)


def _state(conn):
    snap = {t: conn.execute(f'SELECT * FROM {t} ORDER BY 1').fetchall() for t in TABLES}
    snap['stock'] = conn.execute('SELECT sku_key, quantity FROM stock_levels ORDER BY 1').fetchall()
    return {k: [tuple(r) for r in v] for k, v in snap.items()}


def _failing(module, name):
    real = getattr(module, name)

    def wrapper(*args, **kwargs):
        real(*args, **kwargs)  # perform the step's real writes, then fail before commit
        raise Injected(name)
    return mock.patch.object(module, name, wrapper)


def _setup_customer(client, settings, qty):
    email = f'u{next(_counter)}@example.com'
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    login = client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()
    h = {'Authorization': f"Bearer {login['token']}"}
    assert client.post('/api/cart/lines', headers=h, json={'productId': 'p1', 'quantity': qty}).status_code == 200
    conn = db.connect(settings.database_path)
    try:
        uid = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()[0]
    finally:
        conn.close()
    return uid


def _body(mo):
    method, outcome = mo
    data = {'idempotencyKey': f'idem-key-{next(_counter):08d}', 'delivery': DELIVERY, 'method': method}
    if outcome:
        data['outcome'] = outcome
    return CheckoutIn(**data)


def _run_failing(env, qty, mo, target):
    client, settings = env
    uid = _setup_customer(client, settings, qty)
    conn = db.connect(settings.database_path)
    try:
        before = _state(conn)
        with _failing(*target), pytest.raises(Injected):
            service.place_order(conn, uid, _body(mo))
        assert not conn.in_transaction
        assert _state(conn) == before
        # the cart is intact, so the customer can simply retry and succeed
        order, created = service.place_order(conn, uid, _body(mo))
        assert created is True
    finally:
        conn.close()


@hsettings(**PROFILE)
@given(step=step_st, qty=qty_st, mo=method_outcome_st)
def test_single_failure_at_any_step_leaves_no_partial_state(env, step, qty, mo):
    _run_failing(env, qty, mo, STEPS[step])


@hsettings(**PROFILE)
@given(qty=qty_st, mo=st.sampled_from([('fpx', 'failed'), ('ewallet', 'cancelled')]))
def test_failure_during_stock_restore_leaves_no_partial_state(env, qty, mo):
    _run_failing(env, qty, mo, RESTORE_STEP)
