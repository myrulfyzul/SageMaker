"""Property 13: Cart totals invariant.

**Validates: Requirements 11.4, 11.5, 11.7, 11.10**
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
PRODUCTS = ('c1', 'c2', 'c3', 'c4')
DELIVERY_FEE_SEN = 800
_counter = itertools.count()
PROFILE = dict(max_examples=30, deadline=None, suppress_health_check=list(HealthCheck))

# Per product: initial price, quantity in cart, then the state the product is moved to after it is in the cart.
PRODUCT_PLAN = st.fixed_dictionaries({
    'price': st.integers(min_value=1, max_value=500_000),
    'quantity': st.integers(min_value=1, max_value=20),
    'in_cart': st.booleans(),
    'new_price': st.integers(min_value=1, max_value=500_000),
    'new_stock': st.one_of(st.just(0), st.integers(min_value=20, max_value=50)),
    'active': st.booleans(),
    'fake_price': st.integers(min_value=-1000, max_value=10_000_000),
})
PLANS = st.lists(PRODUCT_PLAN, min_size=len(PRODUCTS), max_size=len(PRODUCTS))


def _h(token):
    return {'Authorization': f'Bearer {token}'}


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='cart_prop_'))
        self.settings = Settings(database_path=self.dir / 't.sqlite3', media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(self.settings))
        self.client = self.client_cm.__enter__()

    def _run(self, fn):
        conn = db.connect(self.settings.database_path)
        try:
            with db.transaction(conn):
                fn(conn)
        finally:
            conn.close()

    def reset_products(self, plans):
        def go(conn):
            conn.execute("DELETE FROM stock_levels WHERE product_id LIKE 'c_'")
            conn.execute("DELETE FROM products WHERE id LIKE 'c_'")
            for pid, plan in zip(PRODUCTS, plans):
                conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, "
                             "created_at, updated_at) VALUES (?, ?, '', 1, ?, 1, 'now', 'now')",
                             (pid, f'Name {pid}', plan['price']))
                conn.execute('INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) '
                             'VALUES (?, ?, NULL, 50, 50)', (pid, pid))
        self._run(go)

    def mutate(self, plans):
        def go(conn):
            for pid, plan in zip(PRODUCTS, plans):
                conn.execute('UPDATE products SET price_sen = ?, is_active = ? WHERE id = ?',
                             (plan['new_price'], 1 if plan['active'] else 0, pid))
                conn.execute('UPDATE stock_levels SET quantity = ? WHERE sku_key = ?', (plan['new_stock'], pid))
        self._run(go)

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


def _check_totals(cart, plans):
    by_id = {line['productId']: line for line in cart['lines']}
    subtotal = 0
    any_available = False
    for pid, plan in zip(PRODUCTS, plans):
        if not plan['in_cart']:
            assert pid not in by_id
            continue
        line = by_id[pid]
        # Req 11.4: priced from the current database price, never from client input.
        assert line['unitPriceSen'] == plan['new_price']
        assert line['lineTotalSen'] == plan['new_price'] * plan['quantity']
        expected_available = plan['active'] and plan['new_stock'] > 0
        assert line['available'] is expected_available
        if expected_available:
            subtotal += line['lineTotalSen']
            any_available = True
    # Req 11.7: unavailable lines are excluded; Req 11.5/11.10: subtotal, fee and grand total.
    assert cart['subtotalSen'] == subtotal
    assert cart['deliveryFeeSen'] == (DELIVERY_FEE_SEN if any_available else 0)
    assert cart['grandTotalSen'] == cart['subtotalSen'] + cart['deliveryFeeSen']


@hsettings(**PROFILE)
@given(PLANS)
def test_cart_totals_invariant(plans):
    env = _get_env()
    env.reset_products(plans)
    token = env.customer()
    for pid, plan in zip(PRODUCTS, plans):
        if plan['in_cart']:
            r = env.client.post('/api/cart/lines', headers=_h(token), json={
                'productId': pid, 'quantity': plan['quantity'],
                'unitPriceSen': plan['fake_price'], 'lineTotalSen': plan['fake_price'],
                'grandTotalSen': plan['fake_price'], 'deliveryFeeSen': plan['fake_price']})
            assert r.status_code == 200, r.text
    env.mutate(plans)
    r = env.client.get('/api/cart', headers=_h(token))
    assert r.status_code == 200
    _check_totals(r.json(), plans)
