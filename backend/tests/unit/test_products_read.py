"""Products read side: list filters/sort/pagination, detail visibility, DTO and stock status."""
from __future__ import annotations

from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.modules.inventory import api as inv
from app.modules.products.service import stock_status
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])


def _seed(settings, rows, stock=None):
    """rows: (id, name, description, category_id, price_sen, is_active)."""
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        for pid, name, desc, cat, price, active in rows:
            conn.execute(
                'INSERT INTO products (id, name, description, category_id, price_sen, is_active, is_demo, created_at, updated_at) '
                "VALUES (?, ?, ?, ?, ?, ?, 1, 'now', 'now')", (pid, name, desc, cat, price, active))
            inv.initialise(conn, pid, None, (stock or {}).get(pid, 10), 3)
    conn.close()


def _ids(resp):
    return [i['id'] for i in resp.json()['items']]


def _staff_token(client, settings, role='seller'):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        users_api.create_user(conn, name='S', email=f'{role}@example.com', password_hash=hash_password(PASSWORD), role=role)
    conn.close()
    return client.post('/api/auth/login', json={'email': f'{role}@example.com', 'password': PASSWORD}).json()['token']


def test_list_active_only_search_category_sort_and_paging(client, settings):
    _seed(settings, [
        ('a', 'Tote A', 'Red cotton', 1, 3000, 1),
        ('b', 'Tote B', 'Blue cotton', 1, 3000, 1),
        ('c', 'Toy C', '100% wool_toy', 3, 1000, 1),
        ('d', 'Hidden', 'cotton', 1, 500, 0),
    ])
    r = client.get('/api/products')
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {'items', 'total', 'limit', 'offset'} and body['total'] == 3 and body['limit'] == 20
    assert 'd' not in _ids(r)

    assert _ids(client.get('/api/products', params={'sort': 'price_asc'})) == ['c', 'a', 'b']
    assert _ids(client.get('/api/products', params={'sort': 'price_desc'})) == ['a', 'b', 'c']
    assert _ids(client.get('/api/products', params={'q': 'COTTON'})) == ['a', 'b']
    assert _ids(client.get('/api/products', params={'q': 'cotton', 'category': 'toys'})) == []
    assert _ids(client.get('/api/products', params={'category': 'tote-bags', 'sort': 'price_desc'})) == ['a', 'b']
    # LIKE wildcards are literal
    assert _ids(client.get('/api/products', params={'q': '100%'})) == ['c']
    assert _ids(client.get('/api/products', params={'q': '_toy'})) == ['c']
    assert client.get('/api/products', params={'q': '%'}).json()['total'] == 1
    assert client.get('/api/products', params={'q': 'a_b'}).json()['total'] == 0

    unknown = client.get('/api/products', params={'category': 'nope'}).json()
    assert unknown['items'] == [] and unknown['total'] == 0

    page = client.get('/api/products', params={'sort': 'price_asc', 'limit': 1, 'offset': 1}).json()
    assert [i['id'] for i in page['items']] == ['a'] and page['total'] == 3 and page['offset'] == 1


def test_list_parameter_validation(client):
    for params in ({'q': 'x' * 101}, {'limit': 0}, {'limit': 101}, {'offset': -1}, {'offset': 'x'}, {'sort': 'bad'}):
        r = client.get('/api/products', params=params)
        assert r.status_code == 422 and r.json()['error']['code'] == 'validation_error'
        assert r.json()['error']['details']


def test_detail_dto_and_visibility(client, settings):
    _seed(settings, [('a', 'Tote', 'Nice', 1, 3000, 1), ('x', 'Old', 'gone', 1, 500, 0)], stock={'a': 2})
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("INSERT INTO product_variations (product_id, label, price_delta_sen) VALUES ('a', 'Large', 500)")
        conn.execute("INSERT INTO product_images (product_id, filename, is_demo) VALUES ('a', 'f.jpg', 1)")
    conn.close()

    d = client.get('/api/products/a').json()
    assert d['priceSen'] == 3000 and d['demoPriceSen'] == 3000 and d['isDemo'] is True
    assert d['stock'] == {'status': 'low_stock', 'quantity': 2, 'label': 'Low stock: 2 left'}
    assert d['variations'][0]['priceSen'] == 3500 and d['images'][0]['url'] == '/media/f.jpg'
    assert d['artisan'] is None and d['category']['slug'] == 'tote-bags'

    missing = client.get('/api/products/nope')
    inactive = client.get('/api/products/x')
    assert missing.status_code == inactive.status_code == 404 and missing.json() == inactive.json()
    customer = client.post('/api/auth/register', json={'name': 'C', 'email': 'c@example.com', 'password': PASSWORD})
    ctoken = client.post('/api/auth/login', json={'email': 'c@example.com', 'password': PASSWORD}).json()['token']
    assert client.get('/api/products/x', headers={'Authorization': f'Bearer {ctoken}'}).status_code == 404
    assert customer.status_code == 201
    staff = _staff_token(client, settings)
    r = client.get('/api/products/x', headers={'Authorization': f'Bearer {staff}'})
    assert r.status_code == 200 and r.json()['isActive'] is False


def test_stock_status_boundaries():
    assert stock_status(0, 5)['status'] == 'out_of_stock'
    assert stock_status(1, 5)['label'] == 'Low stock: 1 left'
    assert stock_status(5, 5)['status'] == 'low_stock'
    assert stock_status(6, 5) == {'status': 'in_stock', 'quantity': 6, 'label': 'In stock'}


@hsettings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(query=st.text(alphabet='ab%_\\ A', min_size=1, max_size=4),
       names=st.lists(st.text(alphabet='ab%_\\ A', min_size=1, max_size=8), min_size=1, max_size=6, unique=True))
def test_search_is_literal_case_insensitive_substring(client, settings, query, names):
    """Validates: Requirements 9.2, 28.7"""
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute('DELETE FROM stock_levels')
        conn.execute('DELETE FROM products')
        for i, n in enumerate(names):
            conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, created_at, updated_at) "
                         "VALUES (?, ?, '', 1, 100, 'now', 'now')", (f'p{i}', n))
    conn.close()
    expected = {f'p{i}' for i, n in enumerate(names) if query.lower() in n.lower()}
    resp = client.get('/api/products', params={'q': query, 'limit': 100})
    assert resp.status_code == 200
    assert set(_ids(resp)) == expected and resp.json()['total'] == len(expected)
