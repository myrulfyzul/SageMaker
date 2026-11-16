"""Property 37: Forecast determinism.

**Validates: Requirements 27.13**
"""
from __future__ import annotations

import random

import pandas as pd
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app.modules.forecasting.model import forecast_series

PROFILE = dict(max_examples=100, deadline=None, suppress_health_check=list(HealthCheck))


def _series(values, ym) -> pd.Series:
    idx = pd.period_range(pd.Period(year=ym[0], month=ym[1], freq='M'), periods=len(values), freq='M')
    return pd.Series([float(v) for v in values], index=idx)


@hsettings(**PROFILE)
@given(values=st.lists(st.integers(0, 1000), min_size=1, max_size=48),
       ym=st.tuples(st.integers(2018, 2024), st.integers(1, 12)),
       stock=st.integers(0, 1000), threshold=st.integers(0, 100),
       seed=st.integers(0, 2**32 - 1))
def test_forecast_is_deterministic(values, ym, stock, threshold, seed):
    first = forecast_series(_series(values, ym), stock, threshold)
    # Perturb global RNG state between evaluations: output must not depend on it.
    random.seed(seed)
    second = forecast_series(_series(values, ym), stock, threshold)

    assert first == second
    assert first.to_dict() == second.to_dict()
    assert first.evaluation == second.evaluation
    assert first.selected_model == second.selected_model
    assert first.replenish == second.replenish
