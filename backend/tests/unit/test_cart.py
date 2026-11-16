"""Cart endpoints: pricing, limits, stock, unavailable lines, merge, round trip (Req 11)."""
from __future__ import annotations

from hypothesis import given, settings as hsettings, strategies as st

from app import db

PASSWORD = ''.join(['Secret', '123'])


def _h(token):
    return {'Authorization': f'Bearer {token}'}


def _customer(client, email='a@example.com'):
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    return client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']


def _seed(settings):
    """p1: 1000 sen stock 50; p2: 250 sen stock 3; p3: 500 sen stock 0; v1 variation of p4 (+100) stock 5."""
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        for pid, price, stock in (('p1', 1000, 50), ('p2', 250, 3), ('p3', 500, 0), ('p4', 400, None)):
            conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                         "updated_at) VALUES (?, ?, '', 1, ?, 1, 'now', 'now')", (pid, f'Name {pid}', price))
            if stock is not None:
                conn.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                             "VALUES (?, ?, NULL, ?, ?)", (pid, pid, stock, stock))
        conn.execute("INSERT INTO product_variations (id, product_id, label, price_delta_sen, is_active) "
                     "VALUES (1, 'p4', 'Large', 100, 1)")
        conn.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                     "VALUES ('p4#1', 'p4', 1, 5, 5)")
    conn.close()


def _add(client, t, pid, qty, vid=None):
    return client.post('/api/cart/lines', headers=_h(t), json={'productId': pid, 'variationId': vid, 'quantity': qty})


def test_empty_cart_has_no_delivery_fee(client, settings):
    _seed(settings)
    t = _customer(client)
    body = client.get('/api/cart', headers=_h(t)).json()
    assert body == {'lines': [], 'subtotalSen': 0, 'deliveryFeeSen': 0, 'grandTotalSen': 0}


def test_add_prices_on_server_and_increases_existing(client, settings):
    _seed(settings)
    t = _customer(client)
    r = client.post('/api/cart/lines', headers=_h(t), json={'productId': 'p1', 'quantity': 2, 'unitPriceSen': 1})
    assert r.status_code == 200
    _add(client, t, 'p1', 3)
    _add(client, t, 'p4', 1, 1)
    cart = client.get('/api/cart', headers=_h(t)).json()
    assert [(line['productId'], line['quantity'], line['lineTotalSen']) for line in cart['lines']] == \
        [('p1', 5, 5000), ('p4', 1, 500)]
    assert (cart['subtotalSen'], cart['deliveryFeeSen'], cart['grandTotalSen']) == (5500, 800, 6300)


def test_quantity_range_and_line_limit(client, settings):
    _seed(settings)
    t = _customer(client)
    for bad in (0, 21, -1, 1.5, '2', True, None):
        assert _add(client, t, 'p1', bad).status_code == 422
    assert _add(client, t, 'p1', 15).status_code == 200
    r = _add(client, t, 'p1', 6)
    assert r.status_code == 422 and r.json()['error']['code'] == 'line_limit'
    assert client.get('/api/cart', headers=_h(t)).json()['lines'][0]['quantity'] == 15


def test_stock_conflict_reports_available_and_leaves_cart(client, settings):
    _seed(settings)
    t = _customer(client)
    r = _add(client, t, 'p2', 4)
    assert r.status_code == 409 and r.json()['error']['details'][0]['available'] == 3
    assert client.get('/api/cart', headers=_h(t)).json()['lines'] == []


def test_unavailable_lines_excluded_from_totals(client, settings):
    _seed(settings)
    t = _customer(client)
    _add(client, t, 'p1', 1)
    _add(client, t, 'p2', 1)
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("UPDATE stock_levels SET quantity = 0 WHERE sku_key = 'p2'")
        conn.execute("UPDATE products SET price_sen = 1200 WHERE id = 'p1'")
    cart = client.get('/api/cart', headers=_h(t)).json()
    assert [line['available'] for line in cart['lines']] == [True, False]
    assert (cart['subtotalSen'], cart['deliveryFeeSen'], cart['grandTotalSen']) == (1200, 800, 2000)
    with db.transaction(conn):
        conn.execute("UPDATE products SET is_active = 0 WHERE id = 'p1'")
    conn.close()
    cart = client.get('/api/cart', headers=_h(t)).json()
    assert (cart['subtotalSen'], cart['deliveryFeeSen'], cart['grandTotalSen']) == (0, 0, 0)


def test_set_quantity_zero_and_delete_line(client, settings):
    _seed(settings)
    t = _customer(client)
    _add(client, t, 'p1', 2)
    r = client.put('/api/cart/lines', headers=_h(t), json={'productId': 'p1', 'quantity': 7})
    assert r.json()['lines'][0]['quantity'] == 7
    assert client.put('/api/cart/lines', headers=_h(t), json={'productId': 'p1', 'quantity': 0}).json()['lines'] == []
    line_id = _add(client, t, 'p1', 1).json()['lines'][0]['id']
    assert client.delete(f'/api/cart/lines/{line_id}', headers=_h(t)).json()['lines'] == []
    assert client.delete(f'/api/cart/lines/{line_id}', headers=_h(t)).status_code == 404


def test_merge_sums_caps_and_reports_not_merged(client, settings):
    _seed(settings)
    t = _customer(client)
    _add(client, t, 'p2', 2)
    r = client.post('/api/cart/merge', headers=_h(t), json={'lines': [
        {'productId': 'p1', 'quantity': 4}, {'productId': 'p2', 'quantity': 5},
        {'productId': 'p3', 'quantity': 1}, {'productId': 'nope', 'quantity': 1}]})
    assert r.status_code == 200
    body = r.json()
    qty = {line['productId']: line['quantity'] for line in body['cart']['lines']}
    assert qty == {'p1': 4, 'p2': 3}
    nm = {(n['productId']): (n['quantity'], n['reason']) for n in body['notMerged']}
    assert nm == {'p2': (4, 'insufficient_stock'), 'p3': (1, 'insufficient_stock'), 'nope': (1, 'unavailable')}


def test_cart_requires_customer_and_is_per_user(client, settings):
    _seed(settings)
    assert client.get('/api/cart').status_code == 401
    t1, t2 = _customer(client), _customer(client, 'b@example.com')
    _add(client, t1, 'p1', 1)
    assert client.get('/api/cart', headers=_h(t2)).json()['lines'] == []


@hsettings(max_examples=25, deadline=None)
@given(st.lists(st.tuples(st.sampled_from(['p1', 'p2', 'p3']), st.integers(1, 20)), max_size=8),
       st.sampled_from(['p1', 'p2']), st.integers(1, 3))
def test_invariant_and_add_remove_round_trip(tmp_path_factory, ops, extra_pid, extra_qty):
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
    d = tmp_path_factory.mktemp('cart')
    s = Settings(database_path=d / 't.sqlite3', media_dir=d / 'media', demo_mode=True)
    with TestClient(create_app(s)) as c:
        _seed(s)
        t = _customer(c)
        for pid, q in ops:
            _add(c, t, pid, q)
        before = c.get('/api/cart', headers=_h(t)).json()
        assert before['grandTotalSen'] == sum(line['lineTotalSen'] for line in before['lines'] if line['available']) \
            + before['deliveryFeeSen']
        if all(line['productId'] != extra_pid for line in before['lines']):
            line = _add(c, t, extra_pid, extra_qty).json()['lines']
            lid = next(x['id'] for x in line if x['productId'] == extra_pid)
            after = c.delete(f'/api/cart/lines/{lid}', headers=_h(t)).json()
            assert after == before
