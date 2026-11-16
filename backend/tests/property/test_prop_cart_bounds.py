"""Property 14: Cart quantity bounds and stock limits.

**Validates: Requirements 11.1, 11.2, 11.3, 11.6**
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
PRODUCT = 'p1'
_counter = itertools.count()

# Valid, out-of-range and non-integer quantities.
QUANTITIES = st.one_of(
    st.integers(min_value=-5, max_value=30),
    st.sampled_from([100, 1.5, '3', None, True, False, [], {}]),
)
OPS = st.lists(st.tuples(st.sampled_from(['add', 'set']), QUANTITIES), min_size=1, max_size=15)
STOCK = st.integers(min_value=0, max_value=30)
PROFILE = dict(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='cart_bounds_'))
        self.settings = Settings(database_path=self.dir / 't.sqlite3', media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(self.settings))
        self.client = self.client_cm.__enter__()
        conn = db.connect(self.settings.database_path)
        with db.transaction(conn):
            conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, "
                         "created_at, updated_at) VALUES (?, 'Name', '', 1, 1500, 1, 'now', 'now')", (PRODUCT,))
        conn.close()

    def set_stock(self, quantity):
        conn = db.connect(self.settings.database_path)
        with db.transaction(conn):
            conn.execute('DELETE FROM stock_levels WHERE sku_key = ?', (PRODUCT,))
            conn.execute('INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) '
                         'VALUES (?, ?, NULL, ?, ?)', (PRODUCT, PRODUCT, quantity, quantity))
        conn.close()

    def headers(self):
        email = f'c{next(_counter)}@example.com'
        self.client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
        token = self.client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
        return {'Authorization': f'Bearer {token}'}

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


def _quantity_in_cart(cart) -> int:
    return sum(line['quantity'] for line in cart['lines'] if line['productId'] == PRODUCT)


@hsettings(**PROFILE)
@given(STOCK, OPS)
def test_quantity_never_exceeds_20_or_stock_and_rejections_leave_cart_unchanged(stock, ops):
    env = _get_env()
    env.set_stock(stock)
    headers = env.headers()
    current = 0  # model: quantity of the single line
    for op, qty in ops:
        before = env.client.get('/api/cart', headers=headers).json()
        r = (env.client.post if op == 'add' else env.client.put)(
            '/api/cart/lines', headers=headers, json={'productId': PRODUCT, 'quantity': qty})

        low = 1 if op == 'add' else 0
        if not _is_int(qty) or not low <= qty <= 20:
            expected = 422  # Req 11.2
        else:
            target = current + qty if op == 'add' else qty
            if target > 20:
                expected = 422  # Req 11.3
            elif target > stock:
                expected = 409  # Req 11.6
            else:
                expected = 200  # Req 11.1
        assert r.status_code == expected, (op, qty, current, stock, r.text)

        after = env.client.get('/api/cart', headers=headers).json()
        if expected == 200:
            current = target
            assert r.json()['lines'] == after['lines']
        else:
            assert after == before  # rejected: cart unchanged
            if expected == 409:
                assert 'available' in r.text and str(stock) in r.text  # states the available quantity
        assert _quantity_in_cart(after) == current
        assert current <= 20 and current <= max(stock, 0)
