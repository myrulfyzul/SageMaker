"""Property 36: Backtest metrics and model selection.

**Validates: Requirements 27.3, 27.4, 27.5, 27.9**
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app.modules.forecasting.model import forecast_series

PROFILE = dict(max_examples=100, deadline=None, suppress_health_check=list(HealthCheck))
# Rounding of metrics to 2 decimals can differ by one unit in the last place from an independent float path.
TOL = 0.0100001

counts = st.lists(st.integers(min_value=0, max_value=500), min_size=1, max_size=40)
start_year_month = st.tuples(st.integers(2018, 2024), st.integers(1, 12))


def _series(values, ym) -> pd.Series:
    idx = pd.period_range(pd.Period(year=ym[0], month=ym[1], freq='M'), periods=len(values), freq='M')
    return pd.Series([float(v) for v in values], index=idx)


def _clamp(x: float) -> float:
    return round(max(0.0, float(x)), 2)


def _baseline(train, steps):
    mean = sum(train[-3:]) / len(train[-3:])
    return [_clamp(mean)] * steps


def _candidate(train, first, steps, seasonal):
    """Independent OLS using the normal-equation solver via pinv (model uses lstsq)."""
    n = len(train)

    def row(i):
        r = [1.0, float(i)]
        if seasonal:
            month = (first + i).month
            r += [1.0 if month == m else 0.0 for m in range(2, 13)]
        return r

    x = np.array([row(i) for i in range(n)])
    coef = np.linalg.pinv(x) @ np.array(train, dtype=float)
    return [_clamp(np.array(row(i)) @ coef) for i in range(n, n + steps)]


def _mae_rmse(pred, actual):
    errs = [p - a for p, a in zip(pred, actual)]
    mae = sum(abs(e) for e in errs) / len(errs)
    rmse = math.sqrt(sum(e * e for e in errs) / len(errs))
    return round(mae, 2), round(rmse, 2)


@hsettings(**PROFILE)
@given(values=st.lists(st.integers(0, 500), min_size=6, max_size=40), ym=start_year_month,
       stock=st.integers(0, 1000), threshold=st.integers(0, 100))
def test_backtest_metrics_and_selection(values, ym, stock, threshold):
    result = forecast_series(_series(values, ym), stock, threshold)
    n = len(values)
    first = pd.Period(year=ym[0], month=ym[1], freq='M')
    train, test = values[:-2], values[-2:]
    seasonal = n >= 24

    ev = result.evaluation
    assert ev['available'] is True
    exp_b = _mae_rmse(_baseline(train, 2), test)
    exp_c = _mae_rmse(_candidate(train, first, 2, seasonal), test)

    assert abs(ev['baseline']['mae'] - exp_b[0]) <= TOL
    assert abs(ev['baseline']['rmse'] - exp_b[1]) <= TOL
    assert abs(ev['candidate']['mae'] - exp_c[0]) <= TOL
    assert abs(ev['candidate']['rmse'] - exp_c[1]) <= TOL
    for m in (ev['baseline'], ev['candidate']):
        assert round(m['mae'], 2) == m['mae'] and round(m['rmse'], 2) == m['rmse']

    # Selection rule: candidate iff its reported MAE is strictly lower (ties go to baseline).
    expected = 'candidate' if ev['candidate']['mae'] < ev['baseline']['mae'] else 'baseline'
    assert result.selected_model == expected
    assert result.candidate is not None


@hsettings(**PROFILE)
@given(values=st.lists(st.integers(0, 500), min_size=1, max_size=5), ym=start_year_month,
       stock=st.integers(0, 1000), threshold=st.integers(0, 100))
def test_short_history_baseline_only(values, ym, stock, threshold):
    result = forecast_series(_series(values, ym), stock, threshold)
    assert result.candidate is None
    assert result.selected_model == 'baseline'
    assert result.evaluation == {'available': False, 'reason': 'insufficient_history'}
    assert [p['units'] for p in result.baseline] == _baseline(values, 3)
    payload = result.to_dict()
    assert payload['candidate'] is None
    assert 'mae' not in payload['evaluation'] and 'rmse' not in payload['evaluation']
