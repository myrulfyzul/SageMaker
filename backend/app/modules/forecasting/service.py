"""Forecasting I/O shell (Req 27): reads history and stock, calls the pure core in model.py."""
from __future__ import annotations

import logging
import sqlite3
from typing import Any

import pandas as pd

from app.errors import AppError, NotFound
from app.modules.inventory import api as inventory_api
from app.modules.orders import api as orders_api
from app.modules.products import api as products_api

from .model import forecast_series

logger = logging.getLogger('sagemaker.forecasting')


class ForecastNoHistory(AppError):
    status = 422
    code = 'forecast_no_history'
    message = 'This product has no sales history to forecast from'


class ForecastFailed(AppError):
    status = 500
    code = 'forecast_failed'
    message = 'The forecast could not be calculated'


def forecast(conn: sqlite3.Connection, product_id: str, tz_name: str) -> dict[str, Any]:
    products_api.get_product(conn, product_id, is_staff=True)  # 404 for an unknown product
    rows = orders_api.monthly_units(conn, product_id, tz_name)
    if not rows:
        raise ForecastNoHistory()
    try:
        level = inventory_api.get_level(conn, product_id)
        stock, threshold = level['quantity'], level['lowStockThreshold']
    except NotFound:
        stock, threshold = 0, inventory_api.DEFAULT_LOW_STOCK_THRESHOLD
    synthetic = any(r[2] for r in rows)
    try:
        series = pd.Series([r[1] for r in rows], index=pd.PeriodIndex([r[0] for r in rows], freq='M'), dtype=float)
        result = forecast_series(series, stock, threshold).to_dict()
    except Exception:
        logger.exception('Forecast core failed for product %s', product_id)
        raise ForecastFailed() from None
    return {'productId': product_id, 'synthetic': synthetic, **result}
