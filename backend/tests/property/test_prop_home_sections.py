"""Property 46: Home sections.

**Validates: Requirements 8.2, 8.3, 8.4, 8.5**
"""
from __future__ import annotations

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
PROFILE = dict(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))
LIMIT = 10
NON_REVENUE = ('cancelled', 'payment_failed')
REVENUE_PAY = ('paid', 'pending_cod', 'demo_simulated_not_charged')
BASE = datetime(2025, 1, 1, tzinfo=timezone.utc)


@st.composite
def scenarios(draw):
    n = draw(st.integers(min_value=0, max_value=14))
    products = [{
        'id': f'p{i:02d}',
        'category': draw(st.integers(1, 3)),
        'active': draw(st.booleans()),
        # small range so created_at ties occur
        'created_hours': draw(st.integers(0, 4)),
    } for i in range(n)]
    ids = [p['id'] for p in products] or ['p00']
    orders = draw(st.lists(st.fixed_dictionaries({
        'mine': st.booleans(),
        'status': st.sampled_from(['pending', 'processing', 'shipped', 'delivered', 'cancelled', 'payment_failed']),
        'payment': st.sampled_from(['paid', 'pending_cod', 'demo_simulated_not_charged', 'failed', 'pending']),
        'age_days': st.sampled_from([0, 1, 30, 80, 89, 95, 120]),  # avoids the exact 90-day boundary
        'lines': st.lists(st.tuples(st.sampled_from(ids), st.integers(1, 20)), min_size=1, max_size=3),
    }), max_size=12)) if n else []
    favourites = draw(st.lists(st.sampled_from(ids), max_size=4)) if n else []
    return products, orders, favourites


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='home_prop_'))
        self.settings = Settings(database_path=self.dir / 't.sqlite3', media_dir=self.dir / 'media', demo_mode=True)
        self.cm = TestClient(create_app(self.settings))
        self.client = self.cm.__enter__()
        self.client.post('/api/auth/register', json={'name': 'Aisha', 'email': 'home@example.com', 'password': PASSWORD})
        self.token = self.client.post('/api/auth/login', json={'email': 'home@example.com',
                                                               'password': PASSWORD}).json()['token']
        conn = db.connect(self.settings.database_path)
        self.user_id = conn.execute("SELECT id FROM users WHERE email_lower = 'home@example.com'").fetchone()['id']
        conn.close()

    def seed(self, products, orders, favourites):
        now = datetime.now(timezone.utc)
        conn = db.connect(self.settings.database_path)
        with db.transaction(conn):
            for t in ('order_history', 'order_lines', 'orders', 'favourites', 'product_variations',
                      'product_images', 'products'):
                if t == 'order_history':
                    continue  # append-only; orders deletion would violate FK only if history exists
                conn.execute(f'DELETE FROM {t}')
            for p in products:
                ts = (BASE + timedelta(hours=p['created_hours'])).isoformat()
                conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, "
                             "created_at, updated_at) VALUES (?, ?, '', ?, 100, ?, ?, ?)",
                             (p['id'], f"Name {p['id']}", p['category'], 1 if p['active'] else 0, ts, ts))
            for i, o in enumerate(orders):
                ts = (now - timedelta(days=o['age_days'])).isoformat()
                oid = f'H{self.seq}-{i}'
                conn.execute(
                    "INSERT INTO orders (id, checkout_id, secret_token, customer_name, email, phone, delivery_address, "
                    "payment_method, payment_status, status, shipping_fee_sen, total_sen, items_json, created_at, "
                    "updated_at, user_id, source) VALUES (?, ?, 's', 'n', 'e@example.com', '1', 'a', 'cod', ?, ?, 0, "
                    "100, '[]', ?, ?, ?, 'app')",
                    (oid, f'c-{oid}', o['payment'], o['status'], ts, ts, self.user_id if o['mine'] else None))
                for pid, qty in o['lines']:
                    conn.execute("INSERT INTO order_lines (order_id, product_id, sku_key, name, unit_price_sen, "
                                 "quantity, line_total_sen) VALUES (?, ?, ?, 'n', 100, ?, ?)",
                                 (oid, pid, pid, qty, 100 * qty))
            for pid in set(favourites):
                conn.execute('INSERT INTO favourites (user_id, product_id, created_at) VALUES (?, ?, ?)',
                             (self.user_id, pid, now.isoformat()))
        conn.close()

    seq = 0

    def get(self, path, auth=False):
        h = {'Authorization': f'Bearer {self.token}'} if auth else {}
        r = self.client.get(path, headers=h)
        assert r.status_code == 200
        return [p['id'] for p in r.json()]

    def close(self):
        self.cm.__exit__(None, None, None)
        shutil.rmtree(self.dir, ignore_errors=True)


_env: _Env | None = None


def _get_env() -> _Env:
    global _env
    if _env is None:
        _env = _Env()
    _env.seq += 1
    return _env


def teardown_module(_module):
    global _env
    if _env is not None:
        _env.close()
        _env = None


def _model(products, orders, favourites):
    by_id = {p['id']: p for p in products}
    units: dict[str, int] = {}
    for o in orders:
        if o['status'] in NON_REVENUE or o['payment'] not in REVENUE_PAY or o['age_days'] >= 90:
            continue
        for pid, qty in o['lines']:
            units[pid] = units.get(pid, 0) + qty
    active = [p for p in products if p['active']]
    # units desc, newest first, then id (deterministic final tie-break)
    best = sorted(active, key=lambda p: (-units.get(p['id'], 0), -p['created_hours'], p['id']))
    best_ids = [p['id'] for p in best][:LIMIT]
    new_ids = [p['id'] for p in sorted(active, key=lambda p: (-p['created_hours'], p['id']))][:LIMIT]
    purchased = {pid for o in orders if o['mine'] and o['status'] not in NON_REVENUE for pid, _ in o['lines']}
    signal = set(favourites) | purchased
    if not signal:
        rec_ids = best_ids
    else:
        cats = {by_id[s]['category'] for s in signal if s in by_id}
        rec_ids = [p['id'] for p in best_all(best, cats, purchased)][:LIMIT]
    return best_ids, new_ids, rec_ids, purchased, signal, by_id


def best_all(best_sorted_active, cats, purchased):
    return [p for p in best_sorted_active if p['category'] in cats and p['id'] not in purchased]


@hsettings(**PROFILE)
@given(scenarios())
def test_home_sections(scenario):
    products, orders, favourites = scenario
    env = _get_env()
    env.seed(products, orders, favourites)
    best_ids, new_ids, rec_ids, purchased, signal, by_id = _model(products, orders, favourites)

    # Req 8.2 best sellers: ranking, tie-break, at most 10, active only.
    got_best = env.get('/api/home/best-sellers')
    assert got_best == best_ids
    assert len(got_best) <= LIMIT
    assert all(by_id[i]['active'] for i in got_best)

    # Req 8.3 new arrivals: active, newest first, at most 10.
    got_new = env.get('/api/home/new-arrivals')
    assert got_new == new_ids
    assert len(got_new) <= LIMIT

    # Req 8.5 visitor falls back to best sellers in the same order.
    assert env.get('/api/home/recommendations') == got_best

    # Req 8.4 / 8.5 customer.
    got_rec = env.get('/api/home/recommendations', auth=True)
    assert got_rec == rec_ids
    assert len(got_rec) <= LIMIT
    if not signal:
        assert got_rec == got_best
    else:
        cats = {by_id[s]['category'] for s in signal if s in by_id}
        for pid in got_rec:
            assert by_id[pid]['active']
            assert by_id[pid]['category'] in cats
            assert pid not in purchased


def test_customer_without_signal_gets_best_sellers():
    """Req 8.5 example: only a cancelled order and no favourites means no signal."""
    env = _get_env()
    products = [{'id': 'p00', 'category': 1, 'active': True, 'created_hours': 1},
                {'id': 'p01', 'category': 2, 'active': True, 'created_hours': 2}]
    orders = [{'mine': True, 'status': 'cancelled', 'payment': 'paid', 'age_days': 1, 'lines': [('p00', 3)]}]
    env.seed(products, orders, [])
    assert env.get('/api/home/recommendations', auth=True) == env.get('/api/home/best-sellers')
