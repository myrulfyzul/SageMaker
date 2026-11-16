"""Property tests 3 and 4: money serialisation and configuration validation.

Feature: sagemaker-asia-mobile-platform
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st
from pydantic import BaseModel, ValidationError, field_validator

from app import money
from app.config import (
    DEFAULT_TIMEZONE,
    MAX_TOKEN_LIFETIME,
    MIN_TOKEN_LIFETIME,
    ConfigError,
    Settings,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# Property 3: Money values serialise as JSON integers
# --------------------------------------------------------------------------- #
class PriceOut(BaseModel):
    price_sen: int
    items: list[int]


class PriceIn(BaseModel):
    price_sen: int

    @field_validator('price_sen', mode='before')
    @classmethod
    def _sen(cls, value: object) -> int:
        return money.require_sen(value)


_INT_JSON = re.compile(r'^-?\d+$')


@given(st.integers(min_value=0, max_value=money.MAX_SEN), st.lists(st.integers(0, money.MAX_SEN), max_size=5))
def test_property_3_integers_serialise_without_decimal_or_quotes(amount, others):
    """**Validates: Requirements 1.11**"""
    payload = json.loads(PriceOut(price_sen=amount, items=others).model_dump_json())
    raw = PriceOut(price_sen=amount, items=others).model_dump_json()
    assert f'"price_sen":{amount}' in raw.replace(' ', '')
    assert isinstance(payload['price_sen'], int) and not isinstance(payload['price_sen'], bool)
    assert _INT_JSON.match(str(payload['price_sen']))
    assert all(type(v) is int for v in payload['items'])


@given(
    st.one_of(
        st.floats(allow_nan=True, allow_infinity=True),
        st.text(),
        st.booleans(),
        st.none(),
        st.decimals(allow_nan=False, allow_infinity=False),
    )
)
def test_property_3_non_integer_money_is_rejected(value):
    """**Validates: Requirements 1.11**"""
    with pytest.raises(ValueError):
        money.require_sen(value)
    with pytest.raises(ValidationError):
        PriceIn(price_sen=value)


@given(st.integers(min_value=0, max_value=money.MAX_SEN))
def test_property_3_valid_integer_is_accepted_unchanged(amount):
    """**Validates: Requirements 1.11**"""
    assert money.require_sen(amount) == amount
    assert PriceIn(price_sen=amount).price_sen == amount


# --------------------------------------------------------------------------- #
# Property 4: Configuration validation names the offending variable
# --------------------------------------------------------------------------- #
_NO_FIXTURE = dict(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=100, deadline=None)


def _base_env(tmp_path: Path) -> dict[str, str]:
    return {'DATABASE_PATH': str(tmp_path / 'db.sqlite3')}


def _expect_error(env: dict[str, str], variable: str) -> None:
    with pytest.raises(ConfigError) as info:
        Settings.from_env(env)
    assert info.value.variable == variable
    assert variable in str(info.value)


@pytest.fixture(scope='module')
def work_dir():
    with tempfile.TemporaryDirectory(prefix='sagemaker_cfg_') as d:
        yield Path(d)


out_of_range_lifetime = st.one_of(
    st.integers(max_value=MIN_TOKEN_LIFETIME - 1, min_value=-10**12).map(str),
    st.integers(min_value=MAX_TOKEN_LIFETIME + 1, max_value=10**12).map(str),
    st.text(alphabet='abcxyz.-+ _e', min_size=1).filter(lambda s: s.strip() != '' and not s.strip().isdigit()),
)


@hsettings(**_NO_FIXTURE)
@given(out_of_range_lifetime)
def test_property_4_bad_token_lifetime_names_variable(work_dir, raw):
    """**Validates: Requirements 1.8, 1.9**"""
    _expect_error({**_base_env(work_dir), 'TOKEN_LIFETIME_SECONDS': raw}, 'TOKEN_LIFETIME_SECONDS')


bad_origin = st.one_of(
    st.text(alphabet='abcdefgh', min_size=1),  # no scheme
    st.builds(lambda h: f'ftp://{h}.example', st.text(alphabet='abcdefgh', min_size=1, max_size=8)),
    st.builds(lambda h, p: f'https://{h}.example/{p}', st.text(alphabet='abcdefgh', min_size=1, max_size=8),
              st.text(alphabet='abcdefgh', min_size=1, max_size=8)),
    st.builds(lambda h: f'https://{h}.example?q=1', st.text(alphabet='abcdefgh', min_size=1, max_size=8)),
)
good_origin = st.builds(
    lambda scheme, h, port: f'{scheme}://{h}.example' + (f':{port}' if port else ''),
    st.sampled_from(['http', 'https']),
    st.text(alphabet='abcdefgh', min_size=1, max_size=8),
    st.one_of(st.none(), st.integers(1, 65535)),
)


@hsettings(**_NO_FIXTURE)
@given(st.lists(good_origin, max_size=3), bad_origin, st.integers(0, 3))
def test_property_4_bad_origin_names_variable(work_dir, good, bad, position):
    """**Validates: Requirements 1.8, 1.9**"""
    entries = list(good)
    entries.insert(min(position, len(entries)), bad)
    _expect_error({**_base_env(work_dir), 'ALLOWED_ORIGINS': ','.join(entries)}, 'ALLOWED_ORIGINS')


@hsettings(**_NO_FIXTURE)
@given(st.text(alphabet='abcdefghijklmnop', min_size=1, max_size=12))
def test_property_4_unknown_timezone_names_variable(work_dir, name):
    """**Validates: Requirements 1.8, 1.9**"""
    _expect_error({**_base_env(work_dir), 'APP_TIMEZONE': f'Nowhere/{name}'}, 'APP_TIMEZONE')


@hsettings(**_NO_FIXTURE)
@given(st.text(alphabet='abcdefgh', min_size=1, max_size=8))
def test_property_4_media_dir_that_is_a_file_names_variable(work_dir, name):
    """**Validates: Requirements 1.8, 1.9**"""
    file_path = work_dir / f'file_{name}.txt'
    file_path.write_text('x')
    _expect_error({**_base_env(work_dir), 'MEDIA_DIR': str(file_path)}, 'MEDIA_DIR')


@hsettings(**_NO_FIXTURE)
@given(st.sampled_from([None, '', '   ', '\t']), st.booleans())
def test_property_4_missing_database_path_names_variable(blank, include_other):
    """**Validates: Requirements 1.8, 1.9**"""
    env: dict[str, str] = {'TOKEN_LIFETIME_SECONDS': '7200'} if include_other else {}
    if blank is not None:
        env['DATABASE_PATH'] = blank
    _expect_error(env, 'DATABASE_PATH')


@hsettings(**_NO_FIXTURE)
@given(
    st.integers(MIN_TOKEN_LIFETIME, MAX_TOKEN_LIFETIME),
    st.lists(good_origin, max_size=4),
    st.sampled_from(['Asia/Kuala_Lumpur', 'UTC', 'Asia/Singapore', 'Europe/London']),
    st.text(alphabet='abcdefgh', min_size=1, max_size=8),
    st.booleans(),
)
def test_property_4_valid_combination_round_trips(work_dir, lifetime, origins, tz, media_name, demo):
    """**Validates: Requirements 1.8, 1.9**"""
    media = work_dir / f'media_{media_name}'
    env = {
        **_base_env(work_dir),
        'TOKEN_LIFETIME_SECONDS': str(lifetime),
        'ALLOWED_ORIGINS': ','.join(origins),
        'APP_TIMEZONE': tz,
        'MEDIA_DIR': str(media),
        'DEMO_MODE': '1' if demo else '0',
    }
    parsed = Settings.from_env(env)
    assert parsed.token_lifetime_seconds == lifetime
    assert parsed.allowed_origins == tuple(origins)
    assert parsed.app_timezone == tz
    assert parsed.media_dir == media
    assert parsed.database_path == work_dir / 'db.sqlite3'
    assert parsed.demo_mode is demo


def test_property_4_defaults_when_optional_variables_absent(tmp_path):
    """**Validates: Requirements 1.8, 1.9**"""
    parsed = Settings.from_env(_base_env(tmp_path))
    assert parsed.app_timezone == DEFAULT_TIMEZONE
    assert parsed.allowed_origins == ()
    assert parsed.demo_mode is False


@pytest.mark.parametrize('variable,value', [
    ('TOKEN_LIFETIME_SECONDS', '5'),
    ('APP_TIMEZONE', 'Nowhere/Land'),
    ('ALLOWED_ORIGINS', 'not-an-origin'),
])
def test_property_4_startup_exits_nonzero_naming_variable(tmp_path, variable, value):
    """**Validates: Requirements 1.8, 1.9**"""
    env = {k: v for k, v in os.environ.items() if k not in ('DATABASE_PATH', 'SAGEMAKER_DEMO_DB')}
    env['DATABASE_PATH'] = str(tmp_path / 'db.sqlite3')
    env[variable] = value
    result = subprocess.run(
        [sys.executable, '-c', 'from app.main import application'],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert variable in result.stderr


def test_property_4_startup_exits_nonzero_for_missing_database_path():
    """**Validates: Requirements 1.8, 1.9**"""
    env = {k: v for k, v in os.environ.items() if k not in ('DATABASE_PATH', 'SAGEMAKER_DEMO_DB')}
    result = subprocess.run(
        [sys.executable, '-c', 'from app.main import application'],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert 'DATABASE_PATH' in result.stderr
