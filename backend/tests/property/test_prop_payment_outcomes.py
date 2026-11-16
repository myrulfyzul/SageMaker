"""Property 21: Payment outcome mapping.

**Validates: Requirements 13.1, 13.3, 13.4, 13.5, 13.6, 13.7, 33.7**
"""
from __future__ import annotations

import itertools
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app

PASSWORD = ''.join(['Secret', '123'])
_counter = itertools.count()
PROFILE = dict(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))
INITIAL_STOCK = 50

# (payment status, fulfilment status, record outcome, stock restored)
TABLE = {
    'success': ('paid', 'placed', 'success', False),
    'failed': ('failed', 'payment_failed', 'failed', True),
    'cancelled': ('cancelled', 'cancelled', 'cancelled', True),
}
COD = ('pending_cod', 'placed', 'pending_cod', False)

METHODS = st.sampled_from(['card', 'fpx', 'ewallet', 'cod'])
OUTCOMES = st.sampled_from(['success', 'failed', 'cancelled'])
DELIVERY = {'name': 'Aisha Rahman', 'phone': '0123456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bukit Bintang', 'postcode': '55100', 'state': 'Kuala Lumpur'}


def _h(token):
    return {'Authorization': f'Bearer {token}'}


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='payprop_'))
        self.db_path = self.dir / 't.sqlite3'
        self.settings = Settings(database_path=self.db_path, media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(self.settings))
        self.client = self.client_cm.__enter__()
        self.off_cms = []

    def sql(self, query, params=()):
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                return conn.execute(query, params).fetchall()
        finally:
            conn.close()

    def setup_product(self, price):
        self.sql("DELETE FROM stock_levels WHERE product_id = 'pp1'")
        self.sql("DELETE FROM products WHERE id = 'pp1'")
        self.sql("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                 "updated_at) VALUES ('pp1', 'Pay Product', '', 1, ?, 1, 'now', 'now')", (price,))
        self.sql('INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) '
                 'VALUES (?, ?, NULL, ?, ?)', ('pp1', 'pp1', INITIAL_STOCK, INITIAL_STOCK))

    def stock(self):
        return self.sql("SELECT quantity FROM stock_levels WHERE sku_key = 'pp1'")[0][0]

    def counts(self):
        return (self.sql('SELECT COUNT(*) FROM orders')[0][0], self.sql('SELECT COUNT(*) FROM payments')[0][0])

    def customer_with_cart(self, qty):
        email = f'p{next(_counter)}@example.com'
        self.client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
        token = self.client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
        r = self.client.post('/api/cart/lines', headers=_h(token), json={'productId': 'pp1', 'quantity': qty})
        assert r.status_code == 200, r.text
        return token

    def demo_off_client(self, demo_mode_value=False):
        cm = TestClient(create_app(Settings(database_path=self.db_path, media_dir=self.dir / 'media',
                                            demo_mode=demo_mode_value)))
        self.off_cms.append(cm)
        return cm.__enter__()

    def close(self):
        for cm in self.off_cms:
            cm.__exit__(None, None, None)
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


def _body(method, outcome, key=None, **extra):
    body = {'idempotencyKey': key or f'idem-key-{next(_counter):08d}', 'delivery': DELIVERY, 'method': method}
    if outcome is not None:
        body['outcome'] = outcome
    body.update(extra)
    return body


@hsettings(**PROFILE)
@given(METHODS, OUTCOMES, st.integers(min_value=1, max_value=300_000), st.integers(min_value=1, max_value=5))
def test_checkout_outcome_mapping(method, outcome, price, qty):
    env = _get_env()
    env.setup_product(price)
    token = env.customer_with_cart(qty)
    before = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5)
    # COD must ignore any supplied outcome (Req 13.5); other methods use the outcome table.
    r = env.client.post('/api/checkout', headers=_h(token), json=_body(method, outcome))
    assert r.status_code == 201, r.text
    order = r.json()
    pay_status, fulfilment, record_outcome, restored = COD if method == 'cod' else TABLE[outcome]
    assert order['paymentStatus'] == pay_status
    assert order['status'] == fulfilment
    assert env.stock() == (INITIAL_STOCK if restored else INITIAL_STOCK - qty)

    payments = order['payments']
    assert len(payments) == 1
    p = payments[0]
    assert p['method'] == method and p['outcome'] == record_outcome
    assert isinstance(p['amountSen'], int) and p['amountSen'] > 0
    assert p['amountSen'] == order['totalSen']
    assert p['isDemo'] is True
    stamp = datetime.fromisoformat(p['createdAt'].replace('Z', '+00:00'))
    assert stamp.utcoffset() == timedelta(0)
    assert stamp.replace(tzinfo=None) >= before
    # Exactly one record is stored for the order (Req 13.4).
    assert env.sql('SELECT COUNT(*) FROM payments WHERE order_id = ?', (order['id'],))[0][0] == 1


@hsettings(**PROFILE)
@given(METHODS, OUTCOMES)
def test_demo_mode_off_returns_503_without_side_effects(method, outcome):
    env = _get_env()
    env.setup_product(1000)
    token = env.customer_with_cart(2)
    off = env.demo_off_client(False)
    orders_before, payments_before = env.counts()
    stock_before = env.stock()
    for headers in (_h(token), {}):  # the guard runs before authentication
        r = off.post('/api/checkout', headers=headers, json=_body(method, outcome))
        assert r.status_code == 503, r.text
        assert r.json()['error']['code'] == 'payments_not_configured'
    assert env.counts() == (orders_before, payments_before)
    assert env.stock() == stock_before
    # Cart is untouched.
    cart = env.client.get('/api/cart', headers=_h(token)).json()
    assert [ln['quantity'] for ln in cart['lines']] == [2]


@hsettings(**PROFILE)
@given(st.text(max_size=8).filter(lambda s: s != '1'))
def test_only_exact_one_enables_demo_mode(value):
    s = Settings.from_env({'DATABASE_PATH': str(Path(tempfile.gettempdir()) / 'x.sqlite3'), 'DEMO_MODE': value})
    assert s.demo_mode is False
    s1 = Settings.from_env({'DATABASE_PATH': str(Path(tempfile.gettempdir()) / 'x.sqlite3'), 'DEMO_MODE': '1'})
    assert s1.demo_mode is True


@hsettings(**PROFILE)
@given(METHODS, OUTCOMES, st.sampled_from(['cardNumber', 'cvv', 'expiry', 'card_number', 'iban', 'walletToken']),
       st.text(min_size=1, max_size=20))
def test_card_data_is_rejected(method, outcome, field, value):
    env = _get_env()
    env.setup_product(1000)
    token = env.customer_with_cart(1)
    orders_before, payments_before = env.counts()
    stock_before = env.stock()
    r = env.client.post('/api/checkout', headers=_h(token), json=_body(method, outcome, **{field: value}))
    assert r.status_code == 422, r.text
    assert env.counts() == (orders_before, payments_before)
    assert env.stock() == stock_before
    # The same field smuggled into the delivery object is rejected too.
    bad = _body(method, outcome)
    bad['delivery'] = {**DELIVERY, field: value}
    r = env.client.post('/api/checkout', headers=_h(token), json=bad)
    assert r.status_code == 422, r.text
    assert env.counts() == (orders_before, payments_before)
