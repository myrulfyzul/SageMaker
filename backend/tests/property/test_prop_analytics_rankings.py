"""Property 33: Analytics exclusions and rankings.

**Validates: Requirements 19.3, 19.6, 26.3, 26.4, 26.6**
"""
from __future__ import annotations

import itertools
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app
from app.migrations.runner import run_migrations
from app.modules.analytics import service
from app.modules.analytics.service import InvalidRange, RangeTooLong, STATUSES, aov
from app.modules.orders import api as orders_api
from app.modules.orders.schemas import NewOrder, NewOrderLine
from app.time_utils import today_local

TZ = 'Asia/Kuala_Lumpur'
EXCLUDED = ('cancelled', 'payment_failed')
SHIPPING = 800
PROFILE = dict(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))
_counter = itertools.count()

# A small pool of distinct product names so that equal unit totals (ties) are common.
PRODUCTS = [(f'p{i}', name) for i, name in enumerate(['alpha', 'Beta', 'gamma', 'Delta', 'epsilon', 'zeta', 'Eta',
                                                      'theta'])]
line_st = st.tuples(st.integers(0, len(PRODUCTS) - 1), st.integers(1, 4))
order_st = st.tuples(st.sampled_from(STATUSES), st.lists(line_st, min_size=1, max_size=4, unique_by=lambda x: x[0]),
                     st.integers(100, 5000))
orders_st = st.lists(order_st, min_size=0, max_size=12)


@pytest.fixture(scope='module')
def env():
    d = Path(tempfile.mkdtemp(prefix='analytics_prop_'))
    settings = Settings(database_path=d / 't.sqlite3', media_dir=d / 'media', demo_mode=True)
    cm = TestClient(create_app(settings))
    cm.__enter__()
    yield settings
    cm.__exit__(None, None, None)
    shutil.rmtree(d, ignore_errors=True)


def _fresh_conn(env):
    """A new migrated database per example (order_history is append-only, so rows cannot be deleted)."""
    path = env / f'ex{next(_counter)}.sqlite3'
    run_migrations(path)
    return db.connect(path)


def _seed(conn, orders):
    for status, lines, price in orders:
        key = f'idem-key-{next(_counter):08d}'
        with db.transaction(conn):
            order, _ = orders_api.create_order(conn, NewOrder(
                user_id=1, idempotency_key=key, customer_name='A B', email='a@x.com', phone='0123456789',
                delivery_address='1 Road', payment_method='card',
                payment_status='failed' if status == 'payment_failed' else 'paid', shipping_fee_sen=SHIPPING,
                lines=[NewOrderLine(product_id=PRODUCTS[i][0], variation_id=None, sku_key=PRODUCTS[i][0],
                                    name=PRODUCTS[i][1], unit_price_sen=price, quantity=q) for i, q in lines]))
            orders_api.update_fields(conn, order['id'], status=status)


def _expected(orders):
    eligible = [o for o in orders if o[0] not in EXCLUDED]
    revenue = sum(price * sum(q for _, q in lines) + SHIPPING for _, lines, price in eligible)
    units: dict[str, int] = {}
    for _, lines, _ in eligible:
        for i, q in lines:
            units[i] = units.get(i, 0) + q
    return revenue, len(eligible), units


def _range():
    today = today_local(TZ)
    return today - timedelta(days=1), today + timedelta(days=1)


@hsettings(**PROFILE)
@given(orders=orders_st)
def test_exclusions_and_rankings(env, orders):
    conn = _fresh_conn(env.database_path.parent)
    try:
        _seed(conn, orders)
        start, end = _range()
        out = service.sales(conn, start, end, TZ)
        dash = service.dashboard(conn, TZ)
    finally:
        conn.close()

    revenue, count, units = _expected(orders)
    # Req 19.6 / 26.3: cancelled and payment_failed never contribute to revenue, count, AOV or monthly sales.
    assert out['totalRevenueSen'] == revenue and out['orderCount'] == count
    assert out['aovSen'] == aov(revenue, count)
    assert sum(m['revenueSen'] for m in out['monthly']) == revenue
    assert dash['kpis']['totalRevenueSen'] == revenue and dash['kpis']['orderCount'] == count
    assert sum(m['revenueSen'] for m in dash['salesByMonth']) == revenue

    names = {pid: name for pid, name in PRODUCTS}
    ranked = [(names[f'p{i}'], u) for i, u in units.items()]
    top = sorted(ranked, key=lambda t: (-t[1], t[0].lower()))[:5]
    bottom = sorted(ranked, key=lambda t: (t[1], t[0].lower()))[:5]
    # Req 26.4: top 5 descending units, bottom 5 ascending units, ties by name ascending; no excluded-only products.
    assert [(p['name'], p['units']) for p in out['topProducts']] == top
    assert [(p['name'], p['units']) for p in out['bottomProducts']] == bottom
    assert [(p['name'], p['units']) for p in dash['bestSellers']] == top
    assert len(out['topProducts']) <= 5 and len(out['bottomProducts']) <= 5


def _add_months(day: date, months: int) -> date:
    idx = day.year * 12 + (day.month - 1) + months
    return date(idx // 12, idx % 12 + 1, 1)


@hsettings(max_examples=60, deadline=None, suppress_health_check=list(HealthCheck))
@given(start=st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)),
       offset=st.integers(-400, 1200))
def test_range_validation(env, start, offset):
    end_day = start + timedelta(days=offset)
    if end_day < date(1, 1, 2):
        return
    conn = db.connect(env.database_path)
    try:
        months = (end_day.year - start.year) * 12 + end_day.month - start.month + 1
        if start > end_day:
            with pytest.raises(InvalidRange):
                service.sales(conn, start, end_day, TZ)
        elif months > 24:
            with pytest.raises(RangeTooLong):
                service.sales(conn, start, end_day, TZ)
        else:
            out = service.sales(conn, start, end_day, TZ)
            assert len(out['monthly']) == months
    finally:
        conn.close()


def test_range_boundaries(env):
    conn = db.connect(env.database_path)
    try:
        assert len(service.sales(conn, date(2022, 1, 1), date(2023, 12, 31), TZ)['monthly']) == 24
        with pytest.raises(RangeTooLong):
            service.sales(conn, date(2022, 1, 1), date(2024, 1, 1), TZ)
        with pytest.raises(InvalidRange):
            service.sales(conn, date(2025, 2, 1), date(2025, 1, 31), TZ)
    finally:
        conn.close()
