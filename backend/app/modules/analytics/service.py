"""Dashboard and sales analytics (Req 19.2, 19.3, 19.5, 19.6, 26.1-26.7).

Reads only through other modules' `api` (orders, inventory, production, products). All money is integer sen.
Revenue-eligible orders (not cancelled / payment_failed, Req 19.6) come from `orders.api.sales_rows`.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.errors import AppError
from app.modules.inventory import api as inventory_api
from app.modules.orders import api as orders_api
from app.modules.production import api as production_api
from app.modules.products import api as products_api
from app.time_utils import month_bucket, utc_now

STATUSES = ('placed', 'confirmed', 'preparing', 'shipped', 'delivered', 'cancelled', 'payment_failed')
MAX_RANGE_MONTHS = 24
TOP_N = 5
_ALL_START = '1970-01-01T00:00:00+00:00'
_ALL_END = '9000-01-01T00:00:00+00:00'


class InvalidRange(AppError):
    status = 422
    code = 'invalid_range'
    message = 'The start date must not be after the end date'


class RangeTooLong(AppError):
    status = 422
    code = 'range_too_long'
    message = f'The range must not exceed {MAX_RANGE_MONTHS} months'


def aov(revenue_sen: int, count: int) -> int:
    """Average order value in sen, rounded half up; 0 when there are no orders."""
    return (revenue_sen * 2 + count) // (2 * count) if count > 0 else 0


def _months_between(start: str, end: str) -> list[str]:
    """Inclusive list of 'YYYY-MM' from `start` to `end`."""
    y, m = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    out: list[str] = []
    while (y, m) <= (ey, em):
        out.append(f'{y:04d}-{m:02d}')
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _local_midnight_utc(day: date, tz_name: str) -> str:
    local = datetime.combine(day, time.min, tzinfo=ZoneInfo(tz_name))
    return local.astimezone(timezone.utc).isoformat()


def _monthly(rows: list[dict[str, Any]], months: list[str], tz: str) -> list[dict[str, Any]]:
    series = {m: {'month': m, 'revenueSen': 0, 'orderCount': 0} for m in months}
    for r in rows:
        bucket = series.get(month_bucket(r['createdAt'], tz))
        if bucket is not None:
            bucket['revenueSen'] += r['totalSen']
            bucket['orderCount'] += 1
    return [series[m] for m in months]


def _units_by_product(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    acc: dict[str, dict[str, Any]] = {}
    for r in rows:
        for ln in r['lines']:
            item = acc.setdefault(ln['productId'], {'productId': ln['productId'], 'name': ln['name'], 'units': 0})
            item['units'] += ln['quantity']
    return list(acc.values())


def _top(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda i: (-i['units'], i['name'].lower(), i['productId']))[:TOP_N]


def _bottom(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda i: (i['units'], i['name'].lower(), i['productId']))[:TOP_N]


def sales(conn: sqlite3.Connection, start: date, end: date, tz: str) -> dict[str, Any]:
    if start > end:
        raise InvalidRange()
    months = _months_between(f'{start:%Y-%m}', f'{end:%Y-%m}')
    if len(months) > MAX_RANGE_MONTHS:
        raise RangeTooLong(details=[{'field': 'end', 'reason': f'maximum range is {MAX_RANGE_MONTHS} months'}])
    rows = orders_api.sales_rows(conn, _local_midnight_utc(start, tz), _local_midnight_utc(end + timedelta(days=1), tz))
    monthly = _monthly(rows, months, tz)
    revenue = sum(m['revenueSen'] for m in monthly)  # sum of the series: Req 26.7 holds by construction
    count = sum(m['orderCount'] for m in monthly)
    units = _units_by_product(rows)
    return {'start': start.isoformat(), 'end': end.isoformat(), 'totalRevenueSen': revenue, 'orderCount': count,
            'aovSen': aov(revenue, count), 'monthly': monthly, 'topProducts': _top(units),
            'bottomProducts': _bottom(units)}


def dashboard(conn: sqlite3.Connection, tz: str) -> dict[str, Any]:
    rows = orders_api.sales_rows(conn, _ALL_START, _ALL_END)
    revenue = sum(r['totalSen'] for r in rows)
    count = len(rows)

    now_local = utc_now().astimezone(ZoneInfo(tz))
    y, m = now_local.year, now_local.month - 11
    if m < 1:
        y, m = y - 1, m + 12
    months = _months_between(f'{y:04d}-{m:02d}', f'{now_local.year:04d}-{now_local.month:02d}')

    by_status = {s: orders_api.list_orders(conn, statuses=(s,), limit=1, offset=0)[1] for s in STATUSES}
    return {
        'kpis': {
            'totalRevenueSen': revenue, 'orderCount': count,
            'pendingOrders': by_status['placed'] + by_status['confirmed'], 'aovSen': aov(revenue, count),
            'lowStockCount': inventory_api.low_stock_count(conn),
            'openProductionJobs': production_api.open_job_count(conn),
            'shippedOrderCount': by_status['shipped'],
        },
        'salesByMonth': _monthly(rows, months, tz),
        'ordersByStatus': by_status,
        'bestSellers': _top(_units_by_product(rows)),
        'inventoryByCategory': inventory_api.distribution_by_category(
            conn, products_api.category_names_by_product(conn)),
    }
