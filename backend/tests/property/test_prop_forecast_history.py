"""Property 34: Forecast history construction.

**Validates: Requirements 27.1**

For any set of orders for a product, `orders.api.monthly_units` sums only eligible (not cancelled / payment_failed)
order lines per month, and the forecasting model's `_to_monthly` turns that history into a continuous monthly series
from the first to the last sales month, with months without sales filled with zero.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pandas as pd
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.migrations.runner import run_migrations
from app.modules.forecasting.model import _to_monthly
from app.modules.orders import api as orders
from app.modules.orders.schemas import NewOrder, NewOrderLine

PROFILE = dict(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))
PID = 'p1'

# (months after 2022-01, day 10..18 so the app time zone cannot shift the month, quantity, excluded status or None)
ORDERS = st.lists(
    st.tuples(st.integers(0, 40), st.integers(10, 18), st.integers(1, 6),
              st.sampled_from([None, None, 'cancelled', 'payment_failed'])),
    min_size=0, max_size=12)


def _month(offset: int) -> str:
    return str(pd.Period('2022-01', freq='M') + offset)


@given(ORDERS)
@hsettings(**PROFILE)
def test_forecast_history_is_continuous_zero_filled_and_excludes_failed(spec):
    tmp = Path(tempfile.mkdtemp())
    try:
        path = tmp / 'h.sqlite3'
        run_migrations(path)
        conn = db.connect(path)
        try:
            expected: dict[str, int] = {}
            with db.transaction(conn):
                for i, (off, day, qty, bad) in enumerate(spec):
                    order, _ = orders.create_order(conn, NewOrder(
                        user_id=1, idempotency_key=f'k{i}', customer_name='A B', email='a@x.com',
                        phone='0123456789', delivery_address='1 Road', payment_method='card',
                        payment_status='paid', shipping_fee_sen=0, created_at=f'{_month(off)}-{day:02d}T12:00:00+00:00',
                        lines=[NewOrderLine(product_id=PID, variation_id=None, sku_key=PID, name='T',
                                            unit_price_sen=1000, quantity=qty)]))
                    if bad:
                        conn.execute('UPDATE orders SET status = ? WHERE id = ?', (bad, order['id']))
                    else:
                        expected[_month(off)] = expected.get(_month(off), 0) + qty

            rows = orders.monthly_units(conn, PID)
            assert [(m, u) for m, u, _ in rows] == sorted(expected.items())
            if not rows:
                return

            series = pd.Series([r[1] for r in rows], index=pd.PeriodIndex([r[0] for r in rows], freq='M'),
                               dtype=float)
            monthly = _to_monthly(series)
            first, last = min(expected), max(expected)
            full = pd.period_range(first, last, freq='M')
            assert list(monthly.index) == list(full)  # continuous, ascending
            for period, value in monthly.items():
                assert value == float(expected.get(str(period), 0))  # gaps are zero, no excluded units
        finally:
            conn.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
