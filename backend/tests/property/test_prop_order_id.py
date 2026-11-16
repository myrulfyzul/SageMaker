"""Property 18: Order identifier format.

**Validates: Requirements 14.1**
"""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings, strategies as st

from app import db
from app.migrations.runner import run_migrations
from app.modules.orders import api as orders
from app.modules.orders.schemas import NewOrder, NewOrderLine

ID_RE = re.compile(r'^SM-[A-Z0-9]{10}$')


def _new(key: str) -> NewOrder:
    return NewOrder(
        user_id=1, idempotency_key=key, customer_name='A B', email='a@x.com', phone='0123456789',
        delivery_address='1 Road', payment_method='card', payment_status='paid', shipping_fee_sen=800,
        lines=[NewOrderLine(product_id='p1', variation_id=None, sku_key='p1', name='Thing',
                            unit_price_sen=1000, quantity=1)])


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(count=st.integers(min_value=1, max_value=30))
def test_created_order_ids_match_format_and_are_distinct(count):
    """Property 18: every created Order ID matches ^SM-[A-Z0-9]{10}$ and all are distinct."""
    tmp = Path(tempfile.mkdtemp(prefix='order_id_prop_'))
    conn = None
    try:
        path = tmp / 'orders.sqlite3'
        run_migrations(path)
        conn = db.connect(path)
        ids = []
        with db.transaction(conn):
            for i in range(count):
                order, created = orders.create_order(conn, _new(f'key-{i}'))
                assert created
                ids.append(order['id'])
        assert all(ID_RE.fullmatch(i) for i in ids)
        assert len(set(ids)) == len(ids)
    finally:
        if conn is not None:
            conn.close()
        shutil.rmtree(tmp, ignore_errors=True)


@settings(max_examples=200, deadline=None)
@given(st.integers(min_value=0, max_value=0))
def test_generator_output_matches_format(_):
    assert ID_RE.fullmatch(orders.new_order_id())
