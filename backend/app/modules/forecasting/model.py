"""Pure forecasting core (Req 27). No clock, randomness or I/O: equal inputs give equal outputs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

HORIZON = 3
HOLDOUT = 2
MIN_BACKTEST_HISTORY = 6
MIN_SEASONAL_HISTORY = 24

METHODOLOGY = {
    'data': (
        'Monthly units sold per product, summed per calendar month from orders that count as '
        'revenue, with 0 recorded for months without orders between the first and last month.'
    ),
    'models': (
        'Baseline: the mean of the last three months (or fewer if history is shorter). '
        'Candidate: a least-squares linear trend, with month-of-year seasonal terms only when '
        'at least 24 months of history exist.'
    ),
    'evaluation': (
        'The most recent two months are held out, both models are trained on the earlier months, '
        'and MAE and RMSE in units are measured on the held-out months. The candidate is selected '
        'only when its MAE is strictly lower than the baseline MAE.'
    ),
    'limitations': (
        'Forecasts use sales history only and ignore promotions, price changes and stock-outs. '
        'With a short history the estimates are rough, and the held-out check covers only two months. '
        'Seeded data is synthetic.'
    ),
}


@dataclass(frozen=True)
class ForecastResult:
    history: list  # [{'month': 'YYYY-MM', 'units': int|float}]
    baseline: list  # [{'month', 'units'}] x3
    candidate: Optional[list]  # None when history < 6 months
    evaluation: dict
    selected_model: str  # 'baseline' | 'candidate'
    replenish: bool
    methodology: dict

    def to_dict(self) -> dict:
        return {
            'history': self.history,
            'baseline': {'forecast': self.baseline},
            'candidate': None if self.candidate is None else {'forecast': self.candidate},
            'evaluation': self.evaluation,
            'selectedModel': self.selected_model,
            'replenish': self.replenish,
            'methodology': dict(self.methodology),
        }


def _to_monthly(units: pd.Series) -> pd.Series:
    """Continuous monthly PeriodIndex series, gaps filled with 0 (Req 27.1)."""
    if units is None or len(units) == 0:
        raise ValueError('empty history')
    idx = units.index
    if isinstance(idx, pd.PeriodIndex):
        periods = idx.asfreq('M')
    else:
        periods = pd.PeriodIndex(pd.to_datetime(pd.Index(idx).astype(str)), freq='M')
    s = pd.Series(np.asarray(units, dtype=float), index=periods)
    s = s.groupby(level=0).sum().sort_index()
    full = pd.period_range(s.index[0], s.index[-1], freq='M')
    return s.reindex(full, fill_value=0.0)


def _clamp_round(x: float) -> float:
    return round(max(0.0, float(x)), 2)


def _baseline_predict(train: np.ndarray, steps: int) -> list:
    mean = float(np.mean(train[-min(3, len(train)):]))
    return [_clamp_round(mean)] * steps


def _features(t: np.ndarray, months: np.ndarray, seasonal: bool) -> np.ndarray:
    cols = [np.ones(len(t)), t.astype(float)]
    if seasonal:
        for m in range(2, 13):
            cols.append((months == m).astype(float))
    return np.column_stack(cols)


def _candidate_predict(train: np.ndarray, first_period: pd.Period, steps: int, seasonal: bool) -> list:
    n = len(train)
    t = np.arange(n)
    months = np.array([(first_period + i).month for i in range(n)])
    coef, *_ = np.linalg.lstsq(_features(t, months, seasonal), train, rcond=None)
    ft = np.arange(n, n + steps)
    fm = np.array([(first_period + i).month for i in range(n, n + steps)])
    pred = _features(ft, fm, seasonal) @ coef
    return [_clamp_round(p) for p in pred]


def _metrics(pred: list, actual: np.ndarray) -> dict:
    err = np.asarray(pred, dtype=float) - actual
    return {
        'mae': round(float(np.mean(np.abs(err))), 2),
        'rmse': round(float(np.sqrt(np.mean(err ** 2))), 2),
    }


def _num(x: float):
    return int(x) if float(x).is_integer() else float(x)


def forecast_series(units: pd.Series, stock: int, threshold: int) -> ForecastResult:
    s = _to_monthly(units)
    values = s.to_numpy(dtype=float)
    n = len(values)
    first = s.index[0]
    last = s.index[-1]
    future = [str(last + i) for i in range(1, HORIZON + 1)]

    history = [{'month': str(p), 'units': _num(v)} for p, v in zip(s.index, values)]
    base = _baseline_predict(values, HORIZON)
    baseline = [{'month': m, 'units': u} for m, u in zip(future, base)]

    candidate = None
    if n >= MIN_BACKTEST_HISTORY:
        seasonal = n >= MIN_SEASONAL_HISTORY
        cand = _candidate_predict(values, first, HORIZON, seasonal)
        candidate = [{'month': m, 'units': u} for m, u in zip(future, cand)]
        train, test = values[:-HOLDOUT], values[-HOLDOUT:]
        b_m = _metrics(_baseline_predict(train, HOLDOUT), test)
        c_m = _metrics(_candidate_predict(train, first, HOLDOUT, seasonal), test)
        evaluation = {
            'available': True,
            'holdoutMonths': HOLDOUT,
            'baseline': b_m,
            'candidate': c_m,
        }
        selected = 'candidate' if c_m['mae'] < b_m['mae'] else 'baseline'
    else:
        evaluation = {'available': False, 'reason': 'insufficient_history'}
        selected = 'baseline'

    chosen = candidate if selected == 'candidate' else baseline
    replenish = bool(stock < chosen[0]['units'] + threshold)
    return ForecastResult(
        history=history,
        baseline=baseline,
        candidate=candidate,
        evaluation=evaluation,
        selected_model=selected,
        replenish=replenish,
        methodology=dict(METHODOLOGY),
    )
