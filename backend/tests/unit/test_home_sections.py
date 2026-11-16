"""Home sections: best sellers, new arrivals, recommendations with fallback (Req 8.2 to 8.5)."""
from __future__ import annotations

PASSWORD = ''.join(['Secret', '123'])

from app import db


def _seed(settings):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        # (id, category, active, created_at)
        for pid, cat, active, created in [('a', 1, 1, '2024-01-01'), ('b', 1, 1, '2024-02-01'),
                                          ('c', 2, 1, '2024-03-01'), ('d', 2, 0, '2024-04-01'),
                                          ('e', 3, 1, '2024-05-01')]:
            conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                         "updated_at) VALUES (?, ?, '', ?, 100, ?, ?, ?)", (pid, pid, cat, active, created, created))
    conn.close()


def _ids(resp):
    assert resp.status_code == 200
    return [p['id'] for p in resp.json()]


def _token(client):
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': 'a@example.com', 'password': PASSWORD})
    return client.post('/api/auth/login', json={'email': 'a@example.com', 'password': PASSWORD}).json()['token']


def test_new_arrivals_newest_first_active_only(client, settings):
    _seed(settings)
    assert _ids(client.get('/api/home/new-arrivals')) == ['e', 'c', 'b', 'a']


def test_best_sellers_without_sales_orders_newest_first(client, settings):
    _seed(settings)
    assert _ids(client.get('/api/home/best-sellers')) == ['e', 'c', 'b', 'a']


def test_recommendations_fallback_for_visitor_and_no_signal(client, settings):
    _seed(settings)
    best = _ids(client.get('/api/home/best-sellers'))
    assert _ids(client.get('/api/home/recommendations')) == best
    h = {'Authorization': f'Bearer {_token(client)}'}
    assert _ids(client.get('/api/home/recommendations', headers=h)) == best


def test_recommendations_use_favourite_categories(client, settings):
    _seed(settings)
    h = {'Authorization': f'Bearer {_token(client)}'}
    client.put('/api/favourites/a', headers=h)
    # category 1 holds a and b; both are active and neither was purchased
    assert _ids(client.get('/api/home/recommendations', headers=h)) == ['b', 'a']
