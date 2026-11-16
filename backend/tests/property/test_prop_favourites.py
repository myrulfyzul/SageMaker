"""Property 44: Favourites set semantics.

**Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.9, 10.10**
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
PRODUCTS = ('p1', 'p2', 'p3', 'p4')
IDS = (*PRODUCTS, 'nope')  # 'nope' never exists
_counter = itertools.count()

OPS = st.lists(
    st.tuples(st.sampled_from(['add', 'remove', 'deactivate', 'activate']), st.sampled_from(IDS)),
    max_size=25,
)
ID_LISTS = st.lists(st.sampled_from(IDS), max_size=10)
PROFILE = dict(max_examples=20, deadline=None, suppress_health_check=list(HealthCheck))


def _h(token):
    return {'Authorization': f'Bearer {token}'}


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='fav_prop_'))
        self.settings = Settings(database_path=self.dir / 't.sqlite3', media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(self.settings))
        self.client = self.client_cm.__enter__()
        conn = db.connect(self.settings.database_path)
        with db.transaction(conn):
            for pid in PRODUCTS:
                conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, "
                             "created_at, updated_at) VALUES (?, ?, '', 1, 100, 1, 'now', 'now')",
                             (pid, f'Name {pid}'))
        conn.close()

    def set_active(self, pid, active):
        conn = db.connect(self.settings.database_path)
        with db.transaction(conn):
            conn.execute('UPDATE products SET is_active = ? WHERE id = ?', (1 if active else 0, pid))
        conn.close()

    def reset_products(self):
        conn = db.connect(self.settings.database_path)
        with db.transaction(conn):
            conn.execute('UPDATE products SET is_active = 1')
        conn.close()

    def customer(self):
        email = f'u{next(_counter)}@example.com'
        self.client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
        return self.client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']

    def listed(self, token):
        r = self.client.get('/api/favourites', headers=_h(token))
        assert r.status_code == 200
        return [p['id'] for p in r.json()['items']]

    def close(self):
        self.client_cm.__exit__(None, None, None)
        shutil.rmtree(self.dir, ignore_errors=True)


_env: _Env | None = None


def _get_env() -> _Env:
    global _env
    if _env is None:
        _env = _Env()
    env = _env
    env.reset_products()
    return env


def teardown_module(_module):
    global _env
    if _env is not None:
        _env.close()
        _env = None


@hsettings(**PROFILE)
@given(OPS)
def test_operation_sequences_match_set_model(ops):
    """Req 10.1-10.4, 10.9: list equals the set model; repeats/absent removals are no-ops; inactive hidden but kept."""
    env = _get_env()
    token = env.customer()
    active = set(PRODUCTS)
    model: set[str] = set()  # retained associations
    for op, pid in ops:
        if op == 'add':
            r = env.client.put(f'/api/favourites/{pid}', headers=_h(token))
            if pid in active:
                assert r.status_code == 204
                model.add(pid)
            else:
                assert r.status_code == 409
        elif op == 'remove':
            assert env.client.delete(f'/api/favourites/{pid}', headers=_h(token)).status_code == 204
            model.discard(pid)
        elif op == 'deactivate' and pid in PRODUCTS:
            env.set_active(pid, False)
            active.discard(pid)
        elif op == 'activate' and pid in PRODUCTS:
            env.set_active(pid, True)
            active.add(pid)
        got = env.listed(token)
        assert len(got) == len(set(got))
        assert set(got) == model & active
    # Reactivating everything restores every retained association.
    env.reset_products()
    assert set(env.listed(token)) == model


@hsettings(**PROFILE)
@given(ID_LISTS, ID_LISTS, ID_LISTS, st.booleans())
def test_merge_is_union_of_active_and_order_independent(server_ids, local_a, local_b, deactivate_p4):
    """Req 10.10: merge yields union restricted to active products, independent of merge order."""
    env = _get_env()
    if deactivate_p4:
        env.set_active('p4', False)
    active = set(PRODUCTS) - ({'p4'} if deactivate_p4 else set())

    results = []
    for first, second in ((local_a, local_b), (local_b, local_a)):
        token = env.customer()
        for pid in server_ids:
            env.client.put(f'/api/favourites/{pid}', headers=_h(token))
        for local in (first, second):
            r = env.client.post('/api/favourites/merge', headers=_h(token), json={'productIds': local})
            assert r.status_code == 200
            ids = [p['id'] for p in r.json()['items']]
            assert len(ids) == len(set(ids))
        final = env.listed(token)
        assert len(final) == len(set(final))
        results.append(set(final))

    expected = (set(server_ids) | set(local_a) | set(local_b)) & active
    assert results[0] == results[1] == expected
