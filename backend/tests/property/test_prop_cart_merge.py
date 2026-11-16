"""Property 16: Guest cart merge.

**Validates: Requirements 11.12, 11.13**
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
STOCK = {'p1': 50, 'p2': 3, 'p3': 8, 'p4': 20, 'p5': 0}  # p5 is active but sold out
IDS = (*STOCK, 'nope')  # 'nope' never exists
_counter = itertools.count()

SERVER_CART = st.dictionaries(st.sampled_from([p for p in STOCK if STOCK[p] > 0]), st.integers(1, 20), max_size=4)
GUEST_CART = st.lists(st.tuples(st.sampled_from(IDS), st.integers(1, 20)), max_size=8)
PROFILE = dict(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))


def _h(token):
    return {'Authorization': f'Bearer {token}'}


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='cart_merge_prop_'))
        self.settings = Settings(database_path=self.dir / 't.sqlite3', media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(self.settings))
        self.client = self.client_cm.__enter__()
        conn = db.connect(self.settings.database_path)
        with db.transaction(conn):
            for pid, stock in STOCK.items():
                conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, "
                             "created_at, updated_at) VALUES (?, ?, '', 1, 100, 1, 'now', 'now')",
                             (pid, f'Name {pid}'))
                conn.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                             "VALUES (?, ?, NULL, ?, ?)", (pid, pid, stock, stock))
        conn.close()

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
@given(SERVER_CART, GUEST_CART)
def test_merge_caps_quantities_and_reports_not_merged(server, guest):
    env = _get_env()
    token = env.customer()
    model: dict[str, int] = {}
    for pid, qty in server.items():
        qty = min(qty, STOCK[pid])
        r = env.client.post('/api/cart/lines', headers=_h(token), json={'productId': pid, 'quantity': qty})
        assert r.status_code == 200
        model[pid] = qty

    expected_not_merged: list[tuple[str, int]] = []
    for pid, qty in guest:
        if pid == 'nope':
            expected_not_merged.append((pid, qty))
            continue
        cur = model.get(pid, 0)
        target = min(20, STOCK[pid], cur + qty)
        if target > 0:
            model[pid] = target
        left = qty - (target - cur)
        if left > 0:
            expected_not_merged.append((pid, left))

    r = env.client.post('/api/cart/merge', headers=_h(token),
                        json={'lines': [{'productId': p, 'variationId': None, 'quantity': q} for p, q in guest]})
    assert r.status_code == 200
    body = r.json()
    got = {line['productId']: line['quantity'] for line in body['cart']['lines']}
    assert got == model
    assert all(q <= 20 and q <= STOCK[p] for p, q in got.items())
    assert [(n['productId'], n['quantity']) for n in body['notMerged']] == expected_not_merged
