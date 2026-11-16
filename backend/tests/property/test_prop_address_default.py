"""Property 45: Address book default invariant.

**Validates: Requirements 7.6, 7.7**

For any sequence of address create, update, set-default and delete operations (driven over HTTP), a Customer has
at most one default address, exactly one after any set-default succeeds, and deleting an address never changes the
delivery details stored on existing Orders.
"""
from __future__ import annotations

import itertools
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app

PASSWORD = ''.join(['Secret', '123'])
_counter = itertools.count()


@pytest.fixture(scope='module')
def env():
    with tempfile.TemporaryDirectory(prefix='addr_prop_') as d:
        settings = Settings(database_path=Path(d) / 't.sqlite3', media_dir=Path(d) / 'media', demo_mode=True)
        app = create_app(settings)
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, settings


def _new_customer(client):
    email = f'c{next(_counter)}@example.com'
    assert client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD}).status_code in (200, 201)
    r = client.post('/api/auth/login', json={'email': email, 'password': PASSWORD})
    assert r.status_code == 200
    return {'Authorization': f"Bearer {r.json()['token']}"}, r.json()['user']['id']


def _body(tag: int, is_default: bool) -> dict:
    return {'recipientName': f'R{tag}', 'phone': '0123456789', 'line1': f'{tag} Jalan Satu', 'postcode': '50000',
            'city': 'Kuala Lumpur', 'state': 'Wilayah Persekutuan', 'isDefault': is_default}


def _insert_order(settings, user_id: int, n: int) -> str:
    oid = f'DEMO-PROP{user_id}-{n}'
    conn = db.connect(settings.database_path)
    try:
        with db.transaction(conn):
            conn.execute(
                'INSERT INTO orders (id, checkout_id, secret_token, customer_name, email, phone, delivery_address, '
                'payment_method, payment_status, status, shipping_fee_sen, total_sen, items_json, created_at, '
                'updated_at, user_id, source, delivery_postcode, delivery_state) '
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (oid, f'chk-{oid}', 'tok', 'Aisha', 'a@example.com', '0123456789', '1 Jalan Satu, 50000 KL',
                 'demo_card', 'demo_simulated_not_charged', 'placed', 0, 100, '[]', 't', 't', user_id, 'app',
                 '50000', 'Wilayah Persekutuan'))
    finally:
        conn.close()
    return oid


def _order_snapshot(settings, user_id: int) -> list[tuple]:
    conn = db.connect(settings.database_path)
    try:
        rows = conn.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY id', (user_id,)).fetchall()
        return [tuple(r) for r in rows]
    finally:
        conn.close()


OPS = st.lists(
    st.tuples(st.sampled_from(['create', 'update', 'default', 'delete']), st.integers(0, 9), st.booleans()),
    min_size=1, max_size=20)


@hsettings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(OPS)
def test_address_default_invariant_over_http(env, ops):
    client, settings = env
    headers, uid = _new_customer(client)
    other_headers, other_uid = _new_customer(client)
    other = client.post('/api/me/addresses', json=_body(999, True), headers=other_headers).json()
    orders = [_insert_order(settings, uid, i) for i in range(2)]
    before = _order_snapshot(settings, uid)

    model: dict[int, dict] = {}  # id -> expected body (without isDefault)
    default_id = None
    tag = 0

    for kind, pick, flag in ops:
        ids = list(model)
        if kind == 'create' or not ids:
            tag += 1
            r = client.post('/api/me/addresses', json=_body(tag, flag), headers=headers)
            assert r.status_code == 201
            aid = r.json()['id']
            model[aid] = _body(tag, False)
            if flag:
                default_id = aid
            # creating with isDefault=true leaves exactly one default
            if flag:
                assert r.json()['isDefault'] is True
        else:
            aid = ids[pick % len(ids)]
            if kind == 'update':
                tag += 1
                r = client.put(f'/api/me/addresses/{aid}', json=_body(tag, flag), headers=headers)
                assert r.status_code == 200
                model[aid] = _body(tag, False)
                if flag:
                    default_id = aid
            elif kind == 'default':
                r = client.put(f'/api/me/addresses/{aid}/default', headers=headers)
                assert r.status_code == 200
                default_id = aid
                listed = client.get('/api/me/addresses', headers=headers).json()
                # exactly one default straight after a successful set-default
                assert [a['id'] for a in listed if a['isDefault']] == [aid]
            else:
                assert client.delete(f'/api/me/addresses/{aid}', headers=headers).status_code == 204
                del model[aid]
                if default_id == aid:
                    default_id = None
                # deleted address is gone, deleting again is a 404
                assert client.delete(f'/api/me/addresses/{aid}', headers=headers).status_code == 404

        listed = client.get('/api/me/addresses', headers=headers).json()
        defaults = [a['id'] for a in listed if a['isDefault']]
        assert len(defaults) <= 1
        assert defaults == ([default_id] if default_id is not None else [])
        assert {a['id'] for a in listed} == set(model)
        for a in listed:
            expected = model[a['id']]
            assert all(a[k] == v for k, v in expected.items() if k != 'isDefault')

    # existing orders' delivery details never change, and orders were never removed
    assert _order_snapshot(settings, uid) == before and len(before) == len(orders)
    # another customer's address book is untouched
    other_list = client.get('/api/me/addresses', headers=other_headers).json()
    assert [(a['id'], a['isDefault']) for a in other_list] == [(other['id'], True)]


def test_delete_default_address_leaves_orders_intact(env):
    client, settings = env
    headers, uid = _new_customer(client)
    a = client.post('/api/me/addresses', json=_body(1, True), headers=headers).json()
    _insert_order(settings, uid, 0)
    before = _order_snapshot(settings, uid)
    assert client.delete(f"/api/me/addresses/{a['id']}", headers=headers).status_code == 204
    assert _order_snapshot(settings, uid) == before
    assert client.get('/api/me/addresses', headers=headers).json() == []
