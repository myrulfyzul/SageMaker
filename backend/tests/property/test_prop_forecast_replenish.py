"""Property 38: Replenishment flag and synthetic marker.

**Validates: Requirements 27.6, 27.7**

The replenishment flag is true iff stock < first forecast month of the selected model + threshold, and the
`synthetic` field is true iff at least one contributing order has source `synthetic`.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pandas as pd
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.migrations.runner import run_migrations
from app.modules.forecasting import service
from app.modules.forecasting.model import forecast_series
from app.modules.inventory import api as inventory_api
from app.modules.orders import api as orders
from app.modules.orders.schemas import NewOrder, NewOrderLine

PROFILE = dict(max_examples=60, deadline=None, suppress_health_check=list(HealthCheck))
PID = 'p1'


@given(values=st.lists(st.integers(0, 500), min_size=1, max_size=40), stock=st.integers(0, 1000),
       threshold=st.integers(0, 200))
@hsettings(**PROFILE)
def test_replenish_flag_matches_selected_model_first_month(values, stock, threshold):
    idx = pd.period_range('2021-01', periods=len(values), freq='M')
    result = forecast_series(pd.Series([float(v) for v in values], index=idx), stock, threshold)
    chosen = result.candidate if result.selected_model == 'candidate' else result.baseline
    assert result.selected_model in ('baseline', 'candidate')
    assert result.replenish is (stock < chosen[0]['units'] + threshold)


# (months after 2022-01, quantity, source)
ORDERS = st.lists(st.tuples(st.integers(0, 12), st.integers(1, 20), st.sampled_from(['app', 'synthetic'])),
                  min_size=1, max_size=8)


@given(spec=ORDERS, stock=st.integers(0, 200), threshold=st.integers(0, 50))
@hsettings(**PROFILE)
def test_service_synthetic_marker_and_replenish(spec, stock, threshold):
    tmp = Path(tempfile.mkdtemp())
    try:
        path = tmp / 'r.sqlite3'
        run_migrations(path)
        conn = db.connect(path)
        try:
            with db.transaction(conn):
                conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, "
                             "created_at, updated_at) VALUES (?, 'Bag', '', 1, 1000, 1, 'now', 'now')", (PID,))
                inventory_api.initialise(conn, PID, None, stock, threshold)
                for i, (off, qty, source) in enumerate(spec):
                    month = str(pd.Period('2022-01', freq='M') + off)
                    orders.create_order(conn, NewOrder(
                        user_id=1, idempotency_key=f'k{i}', customer_name='A B', email='a@x.com',
                        phone='0123456789', delivery_address='1 Road', payment_method='card',
                        payment_status='paid', shipping_fee_sen=0, source=source,
                        created_at=f'{month}-15T12:00:00+00:00',
                        lines=[NewOrderLine(product_id=PID, variation_id=None, sku_key=PID, name='Bag',
                                            unit_price_sen=1000, quantity=qty)]))

            out = service.forecast(conn, PID, 'Asia/Kuala_Lumpur')
            assert out['synthetic'] is any(s == 'synthetic' for _, _, s in spec)
            chosen = out['candidate'] if out['selectedModel'] == 'candidate' else out['baseline']
            assert out['replenish'] is (stock < chosen['forecast'][0]['units'] + threshold)
        finally:
            conn.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
