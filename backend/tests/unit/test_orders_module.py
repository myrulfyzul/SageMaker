"""Orders core: create, ids, idempotency, history, legacy mapping, sales queries."""
from __future__ import annotations

import re
import sqlite3

import pytest

from app import db
from app.errors import Conflict
from app.migrations.runner import run_migrations
from app.modules.orders import api as orders
from app.modules.orders.schemas import NewOrder, NewOrderLine
from app.time_utils import utc_now


@pytest.fixture()
def conn(tmp_path):
    path = tmp_path / 'orders.sqlite3'
    run_migrations(path)
    c = db.connect(path)
    yield c
    c.close()


def _new(key='k1', user_id=1, pid='p1', qty=2, **kw):
    return NewOrder(
        user_id=user_id, idempotency_key=key, customer_name='A B', email='a@x.com', phone='0123456789',
        delivery_address='1 Road', payment_method='card', payment_status='paid', shipping_fee_sen=800,
        lines=[NewOrderLine(product_id=pid, variation_id=None, sku_key=pid, name='Thing', unit_price_sen=1000,
                            quantity=qty)], **kw)


def test_create_order_shape_and_totals(conn):
    with db.transaction(conn):
        order, created = orders.create_order(conn, _new())
    assert created
    assert re.fullmatch(r'SM-[A-Z0-9]{10}', order['id'])
    assert order['checkoutId'] == '1:k1'
    assert order['subtotalSen'] == 2000 and order['totalSen'] == 2800
    assert order['lines'][0]['lineTotalSen'] == 2000
    assert [h['newStatus'] for h in order['history']] == ['placed'] and not order['history'][0]['synthetic']
    items = conn.execute('SELECT items_json FROM orders WHERE id = ?', (order['id'],)).fetchone()[0]
    assert '"quantity": 2' in items


def test_idempotent_repeat_writes_nothing(conn):
    with db.transaction(conn):
        first, c1 = orders.create_order(conn, _new())
        second, c2 = orders.create_order(conn, _new())
    assert c1 and not c2 and first['id'] == second['id']
    assert conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 1
    assert conn.execute('SELECT COUNT(*) FROM order_lines').fetchone()[0] == 1
    # same key, different user is a different order
    with db.transaction(conn):
        other, c3 = orders.create_order(conn, _new(user_id=2))
    assert c3 and other['id'] != first['id']


def test_id_collision_retries_then_gives_up(conn):
    with db.transaction(conn):
        a, _ = orders.create_order(conn, _new('a'))
    ids = iter([a['id'], a['id'], 'SM-ZZZZZZZZZZ'])
    with db.transaction(conn):
        b, _ = orders.create_order(conn, _new('b'), id_factory=lambda: next(ids))
    assert b['id'] == 'SM-ZZZZZZZZZZ'
    with pytest.raises(Conflict):
        with db.transaction(conn):
            orders.create_order(conn, _new('c'), id_factory=lambda: a['id'])
    assert conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 2


def test_mark_stock_restored_once(conn):
    with db.transaction(conn):
        o, _ = orders.create_order(conn, _new())
        assert orders.mark_stock_restored(conn, o['id']) is True
        assert orders.mark_stock_restored(conn, o['id']) is False
    assert orders.mark_stock_restored(conn, 'SM-NOPE') is False


def test_legacy_packing_and_synthetic_history(conn):
    conn.execute(
        "INSERT INTO orders (id, checkout_id, secret_token, customer_name, email, phone, delivery_address, "
        "payment_method, payment_status, status, shipping_fee_sen, total_sen, items_json, created_at, updated_at) "
        "VALUES ('DEMO-1', 'legacy-checkout-1', 't', 'A', 'a@x.com', '0', 'addr', 'card', "
        "'demo_simulated_not_charged', 'packing', 800, 800, '[]', '2025-01-01T00:00:00+00:00', 'now')")
    o = orders.get_order(conn, 'DEMO-1')
    assert o['status'] == 'preparing'
    assert o['history'] == [{'previousStatus': None, 'newStatus': 'placed', 'actorUserId': None, 'reason': None,
                             'createdAt': '2025-01-01T00:00:00+00:00', 'synthetic': True}]
    assert conn.execute('SELECT COUNT(*) FROM order_history').fetchone()[0] == 0
    assert conn.execute("SELECT status FROM orders WHERE id='DEMO-1'").fetchone()[0] == 'packing'


def test_history_is_append_only(conn):
    with db.transaction(conn):
        o, _ = orders.create_order(conn, _new())
        orders.append_history(conn, o['id'], 'placed', 'confirmed', 5, None)
    assert [h['newStatus'] for h in orders.get_order(conn, o['id'])['history']] == ['placed', 'confirmed']
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute('DELETE FROM order_history')


def test_sales_queries(conn):
    with db.transaction(conn):
        orders.create_order(conn, _new('a', pid='p1', qty=3))
        orders.create_order(conn, _new('b', user_id=2, pid='p2', qty=1, created_at='2020-01-15T00:00:00+00:00',
                                       source='synthetic'))
        bad, _ = orders.create_order(conn, _new('c', pid='p1', qty=9))
        conn.execute("UPDATE orders SET status='cancelled' WHERE id=?", (bad['id'],))
    assert orders.product_in_any_order(conn, 'p1') and not orders.product_in_any_order(conn, 'zz')
    assert orders.units_sold_since(conn, days=90) == {'p1': 3}
    assert orders.purchased_product_ids(conn, 1) == {'p1'}
    assert orders.purchased_product_ids(conn, 2) == {'p2'}
    year = utc_now().year
    rows = orders.sales_rows(conn, f'{year}-01-01T00:00:00+00:00', f'{year + 1}-01-01T00:00:00+00:00')
    assert len(rows) == 1 and rows[0]['lines'][0]['quantity'] == 3
    assert orders.monthly_units(conn, 'p2') == [('2020-01', 1, True)]
    assert orders.monthly_units(conn, 'p1')[0][1:] == (3, False)
