"""Favourites endpoints: idempotent add/remove, inactive hiding with retention, merge, auth (Req 10)."""
from __future__ import annotations

from hypothesis import given, settings as hsettings, strategies as st

from app import db

PASSWORD = ''.join(['Secret', '123'])


def _h(token):
    return {'Authorization': f'Bearer {token}'}


def _customer(client, email='a@example.com'):
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    return client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']


def _seed(settings, active=('p1', 'p2', 'p3'), inactive=('x1',)):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        for pid in (*active, *inactive):
            conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                         "updated_at) VALUES (?, ?, '', 1, 100, ?, 'now', 'now')",
                         (pid, f'Name {pid}', 1 if pid in active else 0))
    conn.close()


def _ids(client, token):
    return [p['id'] for p in client.get('/api/favourites', headers=_h(token)).json()['items']]


def test_add_is_idempotent_and_remove_is_idempotent(client, settings):
    _seed(settings)
    t = _customer(client)
    assert client.put('/api/favourites/p1', headers=_h(t)).status_code == 204
    assert client.put('/api/favourites/p1', headers=_h(t)).status_code == 204
    assert _ids(client, t) == ['p1']
    assert client.delete('/api/favourites/p1', headers=_h(t)).status_code == 204
    assert client.delete('/api/favourites/p1', headers=_h(t)).status_code == 204
    assert _ids(client, t) == []


def test_add_missing_or_inactive_is_unavailable(client, settings):
    _seed(settings)
    t = _customer(client)
    for pid in ('x1', 'nope'):
        r = client.put(f'/api/favourites/{pid}', headers=_h(t))
        assert r.status_code == 409 and r.json()['error']['code'] == 'product_unavailable'
    assert _ids(client, t) == []


def test_inactive_hidden_but_retained_and_returns_on_reactivation(client, settings):
    _seed(settings)
    t = _customer(client)
    client.put('/api/favourites/p1', headers=_h(t))
    client.put('/api/favourites/p2', headers=_h(t))
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("UPDATE products SET is_active = 0 WHERE id = 'p1'")
    assert _ids(client, t) == ['p2']
    with db.transaction(conn):
        conn.execute("UPDATE products SET is_active = 1 WHERE id = 'p1'")
    conn.close()
    assert sorted(_ids(client, t)) == ['p1', 'p2']


def test_merge_dedupes_and_skips_unavailable(client, settings):
    _seed(settings)
    t = _customer(client)
    client.put('/api/favourites/p1', headers=_h(t))
    r = client.post('/api/favourites/merge', headers=_h(t), json={'productIds': ['p1', 'p2', 'p2', 'x1', 'nope']})
    assert r.status_code == 200
    assert sorted(p['id'] for p in r.json()['items']) == ['p1', 'p2']
    assert client.post('/api/favourites/merge', headers=_h(t), json={'productIds': 'p1'}).status_code == 422


def test_favourites_are_per_user_and_require_customer(client, settings):
    _seed(settings)
    t1, t2 = _customer(client), _customer(client, 'b@example.com')
    client.put('/api/favourites/p1', headers=_h(t1))
    assert _ids(client, t2) == []
    assert client.get('/api/favourites').status_code == 401
    assert client.put('/api/favourites/p1').status_code == 401
    assert client.post('/api/favourites/merge', json={'productIds': []}).status_code == 401


@hsettings(max_examples=25, deadline=None)
@given(st.lists(st.sampled_from(['p1', 'p2', 'p3', 'x1', 'nope']), max_size=12))
def test_merge_never_duplicates(tmp_path_factory, ids):
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
    d = tmp_path_factory.mktemp('fav')
    s = Settings(database_path=d / 't.sqlite3', media_dir=d / 'media', demo_mode=True)
    with TestClient(create_app(s)) as c:
        _seed(s)
        t = _customer(c)
        got = [p['id'] for p in c.post('/api/favourites/merge', headers=_h(t), json={'productIds': ids}).json()['items']]
        assert len(got) == len(set(got))
        assert set(got) == {i for i in ids if i in ('p1', 'p2', 'p3')}
