"""Property 39: Catalogue query semantics.

**Validates: Requirements 9.1, 9.2, 9.4, 9.6, 9.7, 9.8, 20.3, 20.4, 28.7**

For any catalogue of active and inactive Products and any search text (including `%`, `_` and quote characters),
category, sort and pagination values, the result is exactly the active Products matching the text
case-insensitively and the category, ordered by price (as requested) then name; `total` ignores limit/offset;
consecutive pages concatenate to the full result; deactivating then reactivating a Product removes then restores it
and leaves existing Orders intact.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app
from app.modules.products import repository as repo

# ASCII only: SQLite lower() is ASCII-only, matching the case-insensitivity the API promises for catalogue text.
ALPHABET = "abAB_%'\" \\x"
TEXT = st.text(alphabet=ALPHABET, min_size=1, max_size=6)
DESC = st.text(alphabet=ALPHABET, min_size=0, max_size=8)
CATEGORIES = {1: 'tote-bags', 2: 'fabric-books', 3: 'toys', 4: 'gifts', 5: 'accessories'}

PRODUCT = st.fixed_dictionaries({
    'name': TEXT, 'description': DESC, 'category_id': st.integers(1, 5),
    'price_sen': st.integers(1, 5), 'active': st.booleans()})  # small price range forces ties


@pytest.fixture(scope='module')
def env():
    with tempfile.TemporaryDirectory(prefix='cat_prop_') as d:
        settings = Settings(database_path=Path(d) / 't.sqlite3', media_dir=Path(d) / 'media', demo_mode=True)
        app = create_app(settings)
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, settings


def _load(settings, products) -> list[dict]:
    conn = db.connect(settings.database_path)
    try:
        with db.transaction(conn):
            conn.execute('DELETE FROM orders')
            conn.execute('DELETE FROM products')
            for i, p in enumerate(products):
                pid = f'prop-{i:03d}'
                repo.insert_product(conn, product_id=pid, name=p['name'], description=p['description'],
                                    category_id=p['category_id'], price_sen=p['price_sen'], artisan_id=None,
                                    made_to_order=False, now='t')
                repo.set_active(conn, pid, p['active'], 't')
    finally:
        conn.close()
    return [{**p, 'id': f'prop-{i:03d}'} for i, p in enumerate(products)]


def _expected(products, search, category, sort) -> list[str]:
    hits = [p for p in products if p['active']
            and (not search or search.lower() in p['name'].lower() or search.lower() in p['description'].lower())
            and (not category or CATEGORIES[p['category_id']] == category)]
    if sort == 'price_desc':
        hits.sort(key=lambda p: (-p['price_sen'], p['name'], p['id']))
    elif sort == 'price_asc':
        hits.sort(key=lambda p: (p['price_sen'], p['name'], p['id']))
    else:
        hits.sort(key=lambda p: (p['name'], p['id']))
    return [p['id'] for p in hits]


def _get(client, **params):
    r = client.get('/api/products', params={k: v for k, v in params.items() if v is not None})
    assert r.status_code == 200, r.text
    return r.json()


def _orders_snapshot(settings) -> list[tuple]:
    conn = db.connect(settings.database_path)
    try:
        return [tuple(r) for r in conn.execute('SELECT * FROM orders ORDER BY id').fetchall()]
    finally:
        conn.close()


def _insert_order(settings) -> None:
    conn = db.connect(settings.database_path)
    try:
        with db.transaction(conn):
            conn.execute(
                'INSERT INTO orders (id, checkout_id, secret_token, customer_name, email, phone, delivery_address, '
                'payment_method, payment_status, status, shipping_fee_sen, total_sen, items_json, created_at, '
                'updated_at, source, delivery_postcode, delivery_state) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('DEMO-CATPROP', 'chk-catprop', 'tok', 'Aisha', 'a@example.com', '0123456789', '1 Jalan Satu',
                 'demo_card', 'demo_simulated_not_charged', 'placed', 0, 100, '[{"productId":"prop-000"}]',
                 't', 't', 'app', '50000', 'Wilayah Persekutuan'))
    finally:
        conn.close()


@hsettings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(products=st.lists(PRODUCT, min_size=0, max_size=12),
       search=st.one_of(st.none(), TEXT),
       category=st.one_of(st.none(), st.sampled_from(list(CATEGORIES.values()))),
       sort=st.one_of(st.none(), st.sampled_from(['price_asc', 'price_desc'])),
       limit=st.integers(1, 5))
def test_catalogue_query_semantics(env, products, search, category, sort, limit):
    client, settings = env
    loaded = _load(settings, products)
    expected = _expected(loaded, search, category, sort)

    # Full result: exactly the matching active products, in order, with total independent of paging.
    full = _get(client, q=search, category=category, sort=sort, limit=100, offset=0)
    assert [i['id'] for i in full['items']] == expected
    assert full['total'] == len(expected)

    # Pagination: total constant, pages concatenate to the full result.
    collected: list[str] = []
    offset = 0
    while True:
        page = _get(client, q=search, category=category, sort=sort, limit=limit, offset=offset)
        assert page['total'] == len(expected)
        assert page['limit'] == limit and page['offset'] == offset
        assert len(page['items']) <= limit
        collected += [i['id'] for i in page['items']]
        offset += limit
        if offset >= len(expected):
            break
    assert collected == expected

    # Deactivate then reactivate a product: removed, then restored; existing Orders untouched.
    if loaded:
        _insert_order(settings)
        orders_before = _orders_snapshot(settings)
        target = loaded[0]
        conn = db.connect(settings.database_path)
        try:
            with db.transaction(conn):
                repo.set_active(conn, target['id'], False, 't2')
            without = [i['id'] for i in _get(client, q=search, category=category, sort=sort, limit=100)['items']]
            assert target['id'] not in without
            with db.transaction(conn):
                repo.set_active(conn, target['id'], True, 't3')
            restored = [i['id'] for i in _get(client, q=search, category=category, sort=sort, limit=100)['items']]
        finally:
            conn.close()
        reactivated = [dict(p, active=True) if p['id'] == target['id'] else p for p in loaded]
        assert restored == _expected(reactivated, search, category, sort)
        assert _orders_snapshot(settings) == orders_before
