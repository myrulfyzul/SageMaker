"""Property 32: Analytics invariants.

**Validates: Requirements 19.2, 19.3, 26.1, 26.2, 26.7**

For any set of Orders and any valid range: revenue and order count come only from revenue-eligible Orders, AOV is the
integer round-half-up quotient of revenue and count (0 when the count is 0), monthly entries cover every calendar month
overlapping the range in chronological order including zero months, and the monthly revenue sums to the total exactly.
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import DEFAULT_TIMEZONE, Settings
from app.main import create_app
from app.modules.analytics import service

PROFILE = dict(max_examples=60, deadline=None, suppress_health_check=list(HealthCheck))
KL = timedelta(hours=8)  # Asia/Kuala_Lumpur has no DST
EPOCH = datetime(2024, 1, 1, tzinfo=timezone.utc)
STATUSES = ['placed', 'confirmed', 'preparing', 'shipped', 'delivered', 'cancelled', 'payment_failed']
PAYMENTS = ['paid', 'pending_cod', 'demo_simulated_not_charged', 'failed', 'pending']
NON_REVENUE = ('cancelled', 'payment_failed')
REVENUE_PAY = ('paid', 'pending_cod', 'demo_simulated_not_charged')

ORDER = st.fixed_dictionaries({
    'minutes': st.integers(min_value=0, max_value=60 * 24 * 365 * 2),  # two years from EPOCH, month edges included
    'status': st.sampled_from(STATUSES),
    'payment': st.sampled_from(PAYMENTS),
    'subtotal': st.integers(min_value=0, max_value=500_000),
    'shipping': st.sampled_from([0, 800, 1500]),
})
RANGE = st.tuples(st.integers(min_value=0, max_value=700), st.integers(min_value=0, max_value=400))


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='analytics_prop_'))
        settings = Settings(database_path=self.dir / 't.sqlite3', media_dir=self.dir / 'media', demo_mode=True)
        self.app = create_app(settings)
        # Migrations run on app startup; open the lifespan once so the schema exists.
        from fastapi.testclient import TestClient
        self.cm = TestClient(self.app)
        self.cm.__enter__()
        self.conn = db.connect(settings.database_path)
        self.seq = 0

    def seed(self, orders):
        self.seq += 1
        with db.transaction(self.conn):
            self.conn.execute('DELETE FROM order_lines')
            self.conn.execute('DELETE FROM orders')
            for i, o in enumerate(orders):
                oid = f'AN{self.seq}-{i}'
                ts = (EPOCH + timedelta(minutes=o['minutes'])).isoformat()
                self.conn.execute(
                    "INSERT INTO orders (id, checkout_id, secret_token, customer_name, email, phone, delivery_address, "
                    "payment_method, payment_status, status, subtotal_sen, shipping_fee_sen, total_sen, items_json, "
                    "created_at, updated_at, source) VALUES (?, ?, 's', 'n', 'e@example.com', '1', 'a', 'cod', ?, ?, "
                    "?, ?, ?, '[]', ?, ?, 'app')",
                    (oid, f'c-{oid}', o['payment'], o['status'], o['subtotal'], o['shipping'],
                     o['subtotal'] + o['shipping'], ts, ts))

    def close(self):
        self.conn.close()
        self.cm.__exit__(None, None, None)
        shutil.rmtree(self.dir, ignore_errors=True)


_env: _Env | None = None


def _get_env() -> _Env:
    global _env
    if _env is None:
        _env = _Env()
    return _env


def teardown_module(_module):
    global _env
    if _env is not None:
        _env.close()
        _env = None


def _expected_months(start: date, end: date) -> list[str]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f'{y:04d}-{m:02d}')
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


@hsettings(**PROFILE)
@given(st.lists(ORDER, max_size=25), RANGE)
def test_analytics_invariants(orders, rng):
    env = _get_env()
    env.seed(orders)
    start = date(2024, 1, 1) + timedelta(days=rng[0])
    end = start + timedelta(days=rng[1])

    result = service.sales(env.conn, start, end, DEFAULT_TIMEZONE)

    # Independent model: eligible orders whose local (UTC+8) date lies in [start, end].
    eligible = []
    for o in orders:
        local = EPOCH + timedelta(minutes=o['minutes']) + KL
        if o['status'] in NON_REVENUE or o['payment'] not in REVENUE_PAY:
            continue
        if start <= local.date() <= end:
            eligible.append((f'{local.year:04d}-{local.month:02d}', o['subtotal'] + o['shipping']))
    revenue = sum(t for _, t in eligible)
    count = len(eligible)

    assert result['totalRevenueSen'] == revenue                       # Req 26.1
    assert result['orderCount'] == count                              # Req 26.1
    if count == 0:
        assert result['aovSen'] == 0                                  # Req 26.2
    else:
        expected_aov = int((Decimal(revenue) / Decimal(count)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        assert result['aovSen'] == expected_aov                       # Req 26.2

    months = [m['month'] for m in result['monthly']]
    assert months == _expected_months(start, end)                     # chronological, zero months included
    for entry in result['monthly']:
        in_month = [t for mo, t in eligible if mo == entry['month']]
        assert entry['revenueSen'] == sum(in_month)
        assert entry['orderCount'] == len(in_month)
    assert sum(m['revenueSen'] for m in result['monthly']) == result['totalRevenueSen']   # Req 26.7
    assert sum(m['orderCount'] for m in result['monthly']) == result['orderCount']


@hsettings(**PROFILE)
@given(st.lists(ORDER, max_size=25))
def test_dashboard_kpis_use_eligible_orders_only(orders):
    """Req 19.2, 19.3: dashboard revenue, count and AOV are computed from revenue-eligible orders only."""
    env = _get_env()
    env.seed(orders)
    kpis = service.dashboard(env.conn, DEFAULT_TIMEZONE)['kpis']
    totals = [o['subtotal'] + o['shipping'] for o in orders
              if o['status'] not in NON_REVENUE and o['payment'] in REVENUE_PAY]
    assert kpis['totalRevenueSen'] == sum(totals)
    assert kpis['orderCount'] == len(totals)
    expected = (int((Decimal(sum(totals)) / Decimal(len(totals))).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                if totals else 0)
    assert kpis['aovSen'] == expected
