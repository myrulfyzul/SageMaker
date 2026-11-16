"""Pure forecasting core (Req 27.1-27.5, 27.7-27.9, 27.12, 27.13)."""
from __future__ import annotations

import math

import pandas as pd
from hypothesis import given, settings as hsettings, strategies as st

from app.modules.forecasting.model import forecast_series


def _series(vals, start='2024-01'):
    idx = pd.period_range(start, periods=len(vals), freq='M')
    return pd.Series(vals, index=idx)


def test_gaps_filled_with_zero_and_totals_preserved():
    s = pd.Series([5, 7], index=['2025-01', '2025-04'])
    r = forecast_series(s, 0, 0)
    assert [h['month'] for h in r.history] == ['2025-01', '2025-02', '2025-03', '2025-04']
    assert [h['units'] for h in r.history] == [5, 0, 0, 7]


def test_short_history_baseline_only():
    r = forecast_series(_series([4, 6, 8]), 100, 5)
    assert r.candidate is None
    assert r.evaluation == {'available': False, 'reason': 'insufficient_history'}
    assert r.selected_model == 'baseline'
    assert [p['units'] for p in r.baseline] == [6.0, 6.0, 6.0]
    assert [p['month'] for p in r.baseline] == ['2024-04', '2024-05', '2024-06']
    assert 'mae' not in r.evaluation


def test_single_month_uses_that_value():
    r = forecast_series(_series([9]), 0, 0)
    assert [p['units'] for p in r.baseline] == [9.0] * 3


def test_baseline_uses_last_three():
    r = forecast_series(_series([100, 1, 2, 3]), 0, 0)
    assert r.baseline[0]['units'] == 2.0


def test_linear_trend_selects_candidate():
    r = forecast_series(_series([10, 20, 30, 40, 50, 60, 70, 80]), 0, 0)
    assert r.evaluation['available'] and r.evaluation['holdoutMonths'] == 2
    assert r.evaluation['candidate']['mae'] == 0.0
    assert r.evaluation['baseline']['mae'] > 0
    assert r.selected_model == 'candidate'
    assert [p['units'] for p in r.candidate] == [90.0, 100.0, 110.0]


def test_constant_series_tie_goes_to_baseline():
    r = forecast_series(_series([5.0] * 8), 0, 0)
    assert r.evaluation['baseline']['mae'] == r.evaluation['candidate']['mae'] == 0.0
    assert r.selected_model == 'baseline'


def test_exact_metrics_values():
    # train [1,1,1,1], test [3,5]; baseline predicts 1 -> errors 2,4
    r = forecast_series(_series([1, 1, 1, 1, 3, 5]), 0, 0)
    b = r.evaluation['baseline']
    assert b['mae'] == 3.0
    assert b['rmse'] == round(math.sqrt((4 + 16) / 2), 2)


def test_declining_series_clamped_at_zero():
    r = forecast_series(_series([100, 80, 60, 40, 20, 5, 1, 0]), 0, 0)
    assert all(p['units'] >= 0 for p in r.candidate)
    assert r.candidate[-1]['units'] == 0.0


def test_seasonal_only_with_24_months():
    pattern = [10, 12, 30, 12, 10, 8, 9, 11, 13, 40, 14, 10]
    r = forecast_series(_series(pattern * 2), 0, 0)  # 24 months, seasonal
    assert r.candidate is not None and len(r.candidate) == 3
    assert r.evaluation['candidate']['mae'] <= r.evaluation['baseline']['mae']
    r23 = forecast_series(_series((pattern * 2)[:23]), 0, 0)
    assert len(r23.candidate) == 3


def test_replenishment_flag_boundary():
    r = forecast_series(_series([10, 10, 10]), 15, 5)  # forecast 10 + 5 = 15
    assert r.replenish is False
    assert forecast_series(_series([10, 10, 10]), 14, 5).replenish is True


def test_methodology_constant_non_empty():
    a = forecast_series(_series([1, 2, 3]), 0, 0)
    b = forecast_series(_series([9, 9, 9, 9, 9, 9, 9]), 3, 1)
    assert set(a.methodology) == {'data', 'models', 'evaluation', 'limitations'}
    assert all(isinstance(v, str) and v.strip() for v in a.methodology.values())
    assert a.methodology == b.methodology


def test_to_dict_shape():
    d = forecast_series(_series([1, 2, 3]), 0, 0).to_dict()
    assert d['candidate'] is None and d['selectedModel'] == 'baseline'
    assert set(d['baseline']) == {'forecast'}


def test_empty_history_raises():
    try:
        forecast_series(pd.Series([], dtype=float), 0, 0)
    except ValueError:
        return
    raise AssertionError('expected ValueError')


@hsettings(max_examples=60, deadline=None)
@given(st.lists(st.integers(0, 500), min_size=1, max_size=40), st.integers(0, 1000), st.integers(0, 50))
def test_properties_shape_nonneg_deterministic(vals, stock, thr):
    s = _series(vals)
    r = forecast_series(s, stock, thr)
    assert r == forecast_series(s, stock, thr)
    assert len(r.baseline) == 3
    assert (r.candidate is not None) == (len(vals) >= 6)
    assert r.candidate is None or len(r.candidate) == 3
    preds = [p['units'] for p in r.baseline] + [p['units'] for p in (r.candidate or [])]
    assert all(p >= 0 and round(p, 2) == p for p in preds)
    if len(vals) >= 6:
        e = r.evaluation
        cand_wins = e['candidate']['mae'] < e['baseline']['mae']
        assert (r.selected_model == 'candidate') == cand_wins
    else:
        assert r.candidate is None and r.selected_model == 'baseline'
    chosen = r.candidate if r.selected_model == 'candidate' else r.baseline
    assert r.replenish == (stock < chosen[0]['units'] + thr)
