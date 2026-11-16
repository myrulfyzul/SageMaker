"""Contract tests: OpenAPI coverage, integer money fields, error envelope (Req 1.11, 28.5, 31.1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.routing import APIRoute

from app import db
from app.modules.users import api as users_api
from app.security import hash_password
from app.time_utils import today_local

PASSWORD = ''.join(['Secret', '123'])
DELIVERY = {'name': 'Aisha Rahman', 'phone': '0123456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bunga, Taman Indah', 'postcode': '50450', 'state': 'Selangor'}
HTTP_METHODS = {'get', 'post', 'put', 'patch', 'delete'}


def _h(token):
    return {'Authorization': f'Bearer {token}'}


def _walk(node, path='$'):
    """Yield (path, key, value) for every dict entry in a JSON document."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key, value
            yield from _walk(value, f'{path}.{key}')
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk(item, f'{path}[{i}]')


def _money_fields(body):
    return [(p, k, v) for p, k, v in _walk(body) if k.endswith('Sen')]


def _assert_money(body, label):
    fields = _money_fields(body)
    assert fields, f'{label}: expected at least one *Sen field'
    for path, key, value in fields:
        if value is None:
            continue
        assert isinstance(value, int) and not isinstance(value, bool), f'{label}: {path}.{key}={value!r} is not an int'


@pytest.fixture()
def staff(client, settings):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        users_api.create_user(conn, name='S', email='seller@example.com', password_hash=hash_password(PASSWORD),
                              role='seller')
        conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                     "updated_at) VALUES ('p1', 'Bag', '', 1, 1000, 1, 'now', 'now')")
        conn.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                     "VALUES ('p1', 'p1', NULL, 5, 5)")
    conn.close()
    token = client.post('/api/auth/login', json={'email': 'seller@example.com', 'password': PASSWORD}).json()['token']
    return _h(token)


@pytest.fixture()
def customer(client, staff):
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': 'a@example.com', 'password': PASSWORD})
    token = client.post('/api/auth/login', json={'email': 'a@example.com', 'password': PASSWORD}).json()['token']
    return _h(token)


# ---------------------------------------------------------------- OpenAPI

def test_docs_and_openapi_available(client):
    assert client.get('/docs').status_code == 200
    r = client.get('/openapi.json')
    assert r.status_code == 200
    schema = r.json()
    assert schema['openapi'].startswith('3.') and schema['paths']


def test_every_route_is_documented(client, app):
    schema = client.get('/openapi.json').json()
    missing, undescribed = [], []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        for method in route.methods & {m.upper() for m in HTTP_METHODS}:
            op = schema['paths'].get(route.path, {}).get(method.lower())
            if op is None:
                missing.append(f'{method} {route.path}')
            elif not (op.get('summary') or op.get('description')) or not op.get('responses'):
                undescribed.append(f'{method} {route.path}')
    assert not missing, missing
    assert not undescribed, undescribed


def test_schema_money_fields_are_integers(client):
    schema = client.get('/openapi.json').json()
    bad = []
    for name, comp in schema.get('components', {}).get('schemas', {}).items():
        for prop, spec in comp.get('properties', {}).items():
            if not prop.endswith('Sen') and not prop.endswith('_sen'):
                continue
            variants = spec.get('anyOf') or [spec]
            kinds = {v.get('type') for v in variants if v.get('type') != 'null' and '$ref' not in v}
            if not kinds <= {'integer'}:
                bad.append(f'{name}.{prop}: {kinds}')
    assert not bad, bad


# ---------------------------------------------------------------- money fields in real responses

def test_money_fields_are_integers_in_responses(client, staff, customer):
    products = client.get('/api/products')
    assert products.status_code == 200, products.text
    _assert_money(products.json(), 'GET /api/products')

    detail = client.get('/api/products/p1')
    assert detail.status_code == 200, detail.text
    _assert_money(detail.json(), 'GET /api/products/p1')

    added = client.post('/api/cart/lines', headers=customer, json={'productId': 'p1', 'quantity': 2})
    assert added.status_code == 200, added.text
    _assert_money(added.json(), 'POST /api/cart/lines')
    cart = client.get('/api/cart', headers=customer)
    assert cart.status_code == 200
    _assert_money(cart.json(), 'GET /api/cart')

    checkout = client.post('/api/checkout', headers=customer, json={
        'idempotencyKey': 'idem-key-0001', 'delivery': DELIVERY, 'method': 'card', 'outcome': 'success'})
    assert checkout.status_code == 201, checkout.text
    _assert_money(checkout.json(), 'POST /api/checkout')
    order_id = checkout.json()['id']

    for label, url, headers in [
        ('GET /api/orders', '/api/orders', customer),
        (f'GET /api/orders/{order_id}', f'/api/orders/{order_id}', customer),
        ('GET /api/staff/orders', '/api/staff/orders', staff),
        (f'GET /api/staff/orders/{order_id}', f'/api/staff/orders/{order_id}', staff),
        ('GET /api/staff/analytics/dashboard', '/api/staff/analytics/dashboard', staff),
    ]:
        r = client.get(url, headers=headers)
        assert r.status_code == 200, f'{label}: {r.text}'
        _assert_money(r.json(), label)

    today = today_local('Asia/Kuala_Lumpur')
    sales = client.get('/api/staff/analytics/sales', headers=staff, params={
        'start': (today - timedelta(days=1)).isoformat(), 'end': today.isoformat()})
    assert sales.status_code == 200, sales.text
    _assert_money(sales.json(), 'GET /api/staff/analytics/sales')


# ---------------------------------------------------------------- error envelope

def _assert_envelope(r, status, code=None):
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {'error'}
    err = body['error']
    assert isinstance(err['code'], str) and err['code']
    assert isinstance(err['message'], str) and err['message']
    assert set(err) <= {'code', 'message', 'details'}
    if 'details' in err:
        assert isinstance(err['details'], list)
    if code:
        assert err['code'] == code
    return err


def test_error_envelope_shapes(client, customer):
    _assert_envelope(client.get('/api/orders'), 401, 'unauthenticated')
    _assert_envelope(client.get('/api/staff/orders', headers=customer), 403, 'forbidden')
    _assert_envelope(client.get('/api/no-such-route'), 404)
    _assert_envelope(client.get('/api/products/does-not-exist'), 404, 'not_found')
    _assert_envelope(client.delete('/api/health'), 405, 'method_not_allowed')
    err = _assert_envelope(client.post('/api/cart/lines', headers=customer, json={'productId': 'p1'}), 422,
                           'validation_error')
    assert err['details'] and all({'field', 'reason'} <= set(d) for d in err['details'])
