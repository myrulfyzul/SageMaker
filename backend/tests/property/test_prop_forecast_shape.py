"""Property 35: Forecast output shape and non-negativity.

**Validates: Requirements 27.2, 27.4, 27.12**
"""
from __future__ import annotations

import pandas as pd
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app.modules.forecasting.model import forecast_series

PROFILE = dict(max_examples=100, deadline=None, suppress_health_check=list(HealthCheck))

start_year_month = st.tuples(st.integers(2018, 2024), st.integers(1, 12))


def _series(values, ym) -> pd.Series:
    idx = pd.period_range(pd.Period(year=ym[0], month=ym[1], freq='M'), periods=len(values), freq='M')
    return pd.Series([float(v) for v in values], index=idx)


@st.composite
def declining(draw):
    """Strongly declining series (steep slope to 0) to stress the clamp."""
    n = draw(st.integers(1, 40))
    top = draw(st.integers(10, 1000))
    step = top / max(n - 1, 1) * draw(st.sampled_from([1.0, 1.5, 3.0]))
    return [max(0, int(round(top - i * step))) for i in range(n)]


def _check(values, ym, stock, threshold):
    result = forecast_series(_series(values, ym), stock, threshold)
    n = len(values)
    assert len(result.baseline) == 3
    assert all(p['units'] >= 0 for p in result.baseline)
    if n >= 6:
        assert result.candidate is not None
        assert len(result.candidate) == 3
        assert all(p['units'] >= 0 for p in result.candidate)
    else:
        assert result.candidate is None


@hsettings(**PROFILE)
@given(values=st.lists(st.integers(0, 1000), min_size=1, max_size=40), ym=start_year_month,
       stock=st.integers(0, 1000), threshold=st.integers(0, 100))
def test_shape_and_non_negative_arbitrary(values, ym, stock, threshold):
    _check(values, ym, stock, threshold)


@hsettings(**PROFILE)
@given(values=declining(), ym=start_year_month, stock=st.integers(0, 1000), threshold=st.integers(0, 100))
def test_shape_and_non_negative_declining(values, ym, stock, threshold):
    _check(values, ym, stock, threshold)
