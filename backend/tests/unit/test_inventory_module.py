"""Inventory core: initialise, reservation, once-only restoration, low-stock count, ledger invariant."""
from __future__ import annotations

import sqlite3

import pytest
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.errors import Conflict, NotFound, ValidationFailed
from app.migrations.runner import run_migrations
from app.modules.inventory import api as inv


@pytest.fixture()
def conn(tmp_path):
    path = tmp_path / 'inv.sqlite3'
    run_migrations(path)
    c = db.connect(path)
    yield c
    c.close()


def _order(conn, order_id='SM-0000000001'):
    conn.execute(
        "INSERT INTO orders (id, checkout_id, secret_token, customer_name, email, phone, delivery_address, "
        "payment_method, payment_status, status, shipping_fee_sen, total_sen, items_json, created_at, updated_at) "
        "VALUES (?, ?, 't', 'A', 'a@x.com', '0', 'addr', 'card', 'pending', 'placed', 0, 0, '[]', 'now', 'now')",
        (order_id, '1:' + order_id))
    return order_id


def _line(pid, qty, vid=None):
    return {'product_id': pid, 'variation_id': vid, 'quantity': qty}


def _ledger_ok(conn, pid):
    """Req 21.8: current stock == opening stock + sum of deltas."""
    row = conn.execute(
        'SELECT s.quantity - s.opening_quantity - COALESCE((SELECT SUM(delta) FROM stock_adjustments a '
        'WHERE a.sku_key = s.sku_key), 0) AS diff FROM stock_levels s WHERE s.product_id = ?', (pid,)).fetchall()
    return all(r['diff'] == 0 for r in row)


def test_initialise_and_get_level_with_low_stock_flag(conn):
    with db.transaction(conn):
        inv.initialise(conn, 'p1', None, 5, 5)
        inv.initialise(conn, 'p2', None, 6, 5)
        inv.initialise(conn, 'p3', 1, 2, 4)
        inv.initialise(conn, 'p3', 2, 3, 4)
    assert inv.get_level(conn, 'p1')['lowStock'] is True
    assert inv.get_level(conn, 'p2')['lowStock'] is False
    lvl = inv.get_level(conn, 'p3')
    assert lvl['quantity'] == 5 and lvl['lowStock'] is False and len(lvl['variations']) == 2
    assert inv.low_stock_count(conn) == 1
    with pytest.raises(NotFound):
        inv.get_level(conn, 'nope')
    with pytest.raises(Conflict):
        inv.initialise(conn, 'p1', None, 1, 1)
    with pytest.raises(ValidationFailed):
        inv.initialise(conn, 'p9', None, -1, 1)


def test_reserve_success_writes_ledger_and_shortage_changes_nothing(conn):
    with db.transaction(conn):
        inv.initialise(conn, 'a', None, 5, 1)
        inv.initialise(conn, 'b', None, 2, 1)
        oid = _order(conn)
        inv.reserve_for_order(conn, [_line('a', 3), _line('b', 1)], oid, 7)
    assert inv.get_level(conn, 'a')['quantity'] == 2 and _ledger_ok(conn, 'a')
    with db.transaction(conn):
        oid2 = _order(conn, 'SM-0000000002')
        with pytest.raises(Conflict) as exc:
            inv.reserve_for_order(conn, [_line('a', 1), _line('b', 5), _line('ghost', 1)], oid2, 7)
    err = exc.value
    assert err.status == 409 and err.code == 'insufficient_stock'
    assert {d['productId']: d['available'] for d in err.details} == {'b': 1, 'ghost': 0}
    assert inv.get_level(conn, 'a')['quantity'] == 2 and inv.get_level(conn, 'b')['quantity'] == 1
    assert conn.execute('SELECT COUNT(*) FROM stock_adjustments WHERE order_id = ?', ('SM-0000000002',)).fetchone()[0] == 0


def test_restore_happens_once_only(conn):
    with db.transaction(conn):
        inv.initialise(conn, 'a', None, 5, 1)
        oid = _order(conn)
        inv.reserve_for_order(conn, [_line('a', 4)], oid, None)
    with db.transaction(conn):
        assert inv.restore_for_order(conn, oid) is True
    with db.transaction(conn):
        assert inv.restore_for_order(conn, oid) is False
    assert inv.get_level(conn, 'a')['quantity'] == 5 and _ledger_ok(conn, 'a')
    assert conn.execute('SELECT COUNT(*) FROM stock_adjustments WHERE order_id = ? AND delta > 0', (oid,)).fetchone()[0] == 1


def test_check_constraint_blocks_negative_quantity(conn):
    with db.transaction(conn):
        inv.initialise(conn, 'a', None, 1, 1)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute('UPDATE stock_levels SET quantity = -1 WHERE sku_key = ?', ('a',))


def test_distribution_by_category(conn):
    with db.transaction(conn):
        inv.initialise(conn, 'a', None, 4, 1)
        inv.initialise(conn, 'b', None, 6, 1)
        inv.initialise(conn, 'c', None, 1, 1)
    assert inv.distribution_by_category(conn, {'a': 'Toys', 'b': 'Toys', 'c': 'Gifts'}) == [
        {'category': 'Gifts', 'units': 1}, {'category': 'Toys', 'units': 10}]


@hsettings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(initial=st.integers(0, 30), orders=st.lists(st.integers(1, 12), max_size=8))
def test_stock_never_negative_and_equals_initial_minus_sold(tmp_path_factory, initial, orders):
    """Validates: Requirements 14.4, 14.5, 21.8"""
    path = tmp_path_factory.mktemp('p') / 'i.sqlite3'
    run_migrations(path)
    c = db.connect(path)
    try:
        with db.transaction(c):
            inv.initialise(c, 'a', None, initial, 1)
        sold = 0
        for i, qty in enumerate(orders):
            try:
                with db.transaction(c):
                    inv.reserve_for_order(c, [_line('a', qty)], _order(c, f'SM-{i:010d}'), None)
                sold += qty
            except Conflict:
                pass
        level = inv.get_level(c, 'a')['quantity']
        assert level == initial - sold and level >= 0 and _ledger_ok(c, 'a')
    finally:
        c.close()
