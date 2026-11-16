"""Property 10: Ownership isolation.

For any two Customers A and B and any data owned by each (orders, payments, custom orders, notifications,
addresses, favourites, carts), every list and detail request by A returns only A's resources, and a request by A
for B's resource returns the same status and body as a request for a non-existent id and changes nothing.

**Validates: Requirements 6.3, 6.9, 7.8, 15.1, 15.4, 16.5, 17.6, 17.8**
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
from app.modules.notifications import api as notifications_api

PASSWORD = ''.join(['Secret', '123'])
DELIVERY = {'name': 'Aisha Rahman', 'phone': '0123456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bunga, Taman Indah', 'postcode': '50450', 'state': 'Selangor'}
ADDRESS = {'recipientName': 'Aisha', 'phone': '0123456789', 'line1': '1 Jalan Satu', 'postcode': '50450',
           'city': 'Kuala Lumpur', 'state': 'Selangor', 'isDefault': False}
PRODUCTS = ('iso1', 'iso2')
MISSING_INT = 999_999_999
MISSING_ORDER = 'SM-NOSUCHORDER'
_counter = itertools.count()
PROFILE = dict(max_examples=10, deadline=None, suppress_health_check=list(HealthCheck))

# Per customer: (orders, addresses, custom orders, notifications, cart lines, favourites).
SHAPE = st.tuples(st.integers(1, 2), st.integers(1, 3), st.integers(1, 2), st.integers(1, 3),
                  st.integers(1, 2), st.integers(1, 2))


def _h(token):
    return {'Authorization': f'Bearer {token}'}


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='ownership_prop_'))
        self.db_path = self.dir / 't.sqlite3'
        settings = Settings(database_path=self.db_path, media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(settings))
        self.client = self.client_cm.__enter__()
        for p in PRODUCTS:
            self.sql("INSERT INTO products (id, name, description, category_id, price_sen, is_active, "
                     "created_at, updated_at) VALUES (?, ?, '', 1, 1000, 1, 'now', 'now')", (p, f'Name {p}'))
            self.sql("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                     "VALUES (?, ?, NULL, 100000, 100000)", (p, p))

    def sql(self, query, params=()):
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                return [tuple(r) for r in conn.execute(query, params).fetchall()]
        finally:
            conn.close()

    def snapshot(self):
        """Every table except sessions and migration bookkeeping, as sorted rows."""
        names = [r[0] for r in self.sql("SELECT name FROM sqlite_master WHERE type = 'table' "
                                        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        skip = ('session', 'token', 'attempt', 'schema_migrations')
        return {n: sorted(map(repr, self.sql(f'SELECT * FROM "{n}"'))) for n in names
                if not any(s in n for s in skip)}

    def customer(self, shape):
        n_orders, n_addr, n_custom, n_notes, n_cart, n_fav = shape
        email = f'o{next(_counter)}@example.com'
        c = self.client
        c.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
        token = c.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
        user_id = self.sql('SELECT id FROM users WHERE email = ?', (email,))[0][0]
        res = {'token': token, 'user_id': user_id, 'orders': [], 'addresses': [], 'custom': [], 'notes': [],
               'cart': [], 'favs': list(PRODUCTS[:n_fav])}
        for i in range(n_orders):
            assert c.post('/api/cart/lines', headers=_h(token),
                          json={'productId': PRODUCTS[0], 'quantity': 1}).status_code == 200
            r = c.post('/api/checkout', headers=_h(token), json={
                'idempotencyKey': f'idem-{next(_counter):08d}', 'delivery': DELIVERY, 'method': 'card',
                'outcome': 'failed' if i % 2 else 'success'})
            assert r.status_code == 201, r.text
            res['orders'].append(r.json()['id'])
        for _ in range(n_addr):
            r = c.post('/api/me/addresses', headers=_h(token), json=ADDRESS)
            assert r.status_code == 201, r.text
            res['addresses'].append(r.json()['id'])
        for _ in range(n_custom):
            r = c.post('/api/custom-orders', headers=_h(token), data={
                'productType': 'Vase', 'description': 'A hand made ceramic vase', 'quantity': '1',
                'preferredDate': '2099-01-01'})
            assert r.status_code == 201, r.text
            res['custom'].append(r.json()['id'])
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                res['notes'] = [notifications_api.create(conn, user_id, 'system', f'T{i}', 'Body')
                                for i in range(n_notes)]
        finally:
            conn.close()
        for pid in PRODUCTS[:n_cart]:
            assert c.post('/api/cart/lines', headers=_h(token),
                          json={'productId': pid, 'quantity': 1}).status_code == 200
        res['cart'] = [r[0] for r in self.sql('SELECT id FROM cart_lines WHERE user_id = ?', (user_id,))]
        for pid in res['favs']:
            assert c.put(f'/api/favourites/{pid}', headers=_h(token)).status_code == 204
        return res

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


def _ids(body):
    return [item['id'] for item in (body if isinstance(body, list) else body['items'])]


@hsettings(**PROFILE)
@given(SHAPE, SHAPE)
def test_foreign_resources_look_like_missing_ones_and_nothing_changes(shape_a, shape_b):
    env = _get_env()
    a, b = env.customer(shape_a), env.customer(shape_b)
    c, ha = env.client, _h(a['token'])

    # Lists contain only A's resources.
    assert set(_ids(c.get('/api/orders', headers=ha, params={'limit': 50}).json())) == set(a['orders'])
    assert set(_ids(c.get('/api/me/addresses', headers=ha).json())) == set(a['addresses'])
    assert set(_ids(c.get('/api/custom-orders', headers=ha, params={'limit': 50}).json())) == set(a['custom'])
    notes = c.get('/api/notifications', headers=ha, params={'limit': 50}).json()
    own = {r[0] for r in env.sql('SELECT id FROM notifications WHERE user_id = ?', (a['user_id'],))}
    assert set(_ids(notes)) == own and set(a['notes']) <= own
    assert len(c.get('/api/cart', headers=ha).json()['lines']) == len(a['cart'])
    assert sorted(i['id'] for i in c.get('/api/favourites', headers=ha).json()['items']) == sorted(a['favs'])

    # (label, B's id, a missing id, request builder)
    cases = []
    for oid in b['orders']:
        cases += [
            (lambda i: c.get(f'/api/orders/{i}', headers=ha), oid, MISSING_ORDER),
            (lambda i: c.get(f'/api/orders/{i}/payments', headers=ha), oid, MISSING_ORDER),
            (lambda i: c.post(f'/api/orders/{i}/payments', headers=ha,
                              json={'method': 'card', 'outcome': 'success'}), oid, MISSING_ORDER),
        ]
    for aid in b['addresses']:
        cases += [
            (lambda i: c.put(f'/api/me/addresses/{i}', headers=ha, json=ADDRESS), aid, MISSING_INT),
            (lambda i: c.put(f'/api/me/addresses/{i}/default', headers=ha), aid, MISSING_INT),
            (lambda i: c.delete(f'/api/me/addresses/{i}', headers=ha), aid, MISSING_INT),
        ]
    for cid in b['custom']:
        cases.append((lambda i: c.get(f'/api/custom-orders/{i}', headers=ha), cid, MISSING_INT))
    for nid in b['notes']:
        cases.append((lambda i: c.post(f'/api/notifications/{i}/read', headers=ha), nid, MISSING_INT))
    for lid in b['cart']:
        cases.append((lambda i: c.delete(f'/api/cart/lines/{i}', headers=ha), lid, MISSING_INT))

    for request, foreign_id, missing_id in cases:
        before = env.snapshot()
        missing = request(missing_id)
        assert missing.status_code == 404, missing.text
        assert env.snapshot() == before
        foreign = request(foreign_id)
        assert foreign.status_code == missing.status_code
        assert foreign.json() == missing.json()
        assert env.snapshot() == before  # nothing changed for either customer

    # A's removing a favourite B shares never touches B's favourites.
    before_b = c.get('/api/favourites', headers=_h(b['token'])).json()
    assert c.delete(f'/api/favourites/{PRODUCTS[0]}', headers=ha).status_code == 204
    assert c.get('/api/favourites', headers=_h(b['token'])).json() == before_b
