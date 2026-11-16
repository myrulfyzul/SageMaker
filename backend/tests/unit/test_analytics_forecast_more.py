"""Additional analytics, settings and forecasting cases (Req 19.9, 26.6, 27.4, 27.10, 31.1)."""
from __future__ import annotations

import pytest

from app import db
from app.modules.forecasting import service as forecast_service
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])
SALES = '/api/staff/analytics/sales'
SETTINGS = '/api/staff/settings'


def _login(client, settings, role):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        users_api.create_user(conn, name='U', email=f'{role}@example.com', password_hash=hash_password(PASSWORD),
                              role=role)
    conn.close()
    token = client.post('/api/auth/login', json={'email': f'{role}@example.com', 'password': PASSWORD}).json()['token']
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture()
def staff(client, settings):
    return _login(client, settings, 'seller')


@pytest.fixture()
def product_id(client, staff):
    body = {'name': 'Tote', 'description': 'Nice', 'categoryId': 1, 'priceSen': 3000, 'stock': 10}
    return client.post('/api/staff/products', json=body, headers=staff).json()['id']


# --- Dashboard with no data: every figure is zero (Req 19.9, 26.6) ---
def test_empty_dashboard_all_zero(client, staff):
    body = client.get('/api/staff/analytics/dashboard', headers=staff).json()
    kpis = body['kpis']
    assert kpis['totalRevenueSen'] == 0 and kpis['orderCount'] == 0 and kpis['aovSen'] == 0
    assert kpis['pendingOrders'] == 0
    assert all(v == 0 for v in body['ordersByStatus'].values())
    assert body['bestSellers'] == []


# --- Range validation (Req 26.6) ---
@pytest.mark.parametrize('params', [
    {}, {'start': '2025-01-01'}, {'end': '2025-01-01'},
    {'start': 'not-a-date', 'end': '2025-01-01'}, {'start': '2025-13-45', 'end': '2025-12-01'},
])
def test_sales_missing_or_malformed_dates_422(client, staff, params):
    assert client.get(SALES, params=params, headers=staff).status_code == 422


def test_sales_single_day_and_exact_limit(client, staff):
    r = client.get(SALES, params={'start': '2025-03-10', 'end': '2025-03-10'}, headers=staff)
    assert r.status_code == 200 and len(r.json()['monthly']) == 1 and r.json()['totalRevenueSen'] == 0
    over = client.get(SALES, params={'start': '2022-01-01', 'end': '2024-01-01'}, headers=staff)
    assert over.status_code == 422 and over.json()['error']['code'] == 'range_too_long'


# --- Settings failure path (Req 31.1) ---
def test_settings_invalid_body_leaves_value_unchanged(client, staff):
    assert client.put(SETTINGS, headers=staff, json={'defaultLowStockThreshold': 7}).status_code == 200
    assert client.put(SETTINGS, headers=staff, json={'defaultLowStockThreshold': None}).status_code == 422
    assert client.put(SETTINGS, headers=staff, json={'defaultLowStockThreshold': '7'}).status_code in (200, 422)
    assert client.get(SETTINGS, headers=staff).json()['defaultLowStockThreshold'] in (7,)


# --- Forecast through the endpoint (Req 27.4, 27.10) ---
def _rows(n, pattern):
    months = [f'{2023 + i // 12}-{i % 12 + 1:02d}' for i in range(n)]
    return [(m, pattern[i % len(pattern)], False) for i, m in enumerate(months)]


def test_endpoint_short_history_baseline_only(client, staff, product_id, monkeypatch):
    monkeypatch.setattr(forecast_service.orders_api, 'monthly_units', lambda *a, **k: _rows(3, [4, 6, 8]))
    body = client.get(f'/api/staff/forecast/{product_id}', headers=staff).json()
    assert body['candidate'] is None and body['selectedModel'] == 'baseline'
    assert body['evaluation'] == {'available': False, 'reason': 'insufficient_history'}


def test_endpoint_seasonal_history_24_months(client, staff, product_id, monkeypatch):
    pattern = [10, 12, 30, 12, 10, 8, 9, 11, 13, 40, 14, 10]
    monkeypatch.setattr(forecast_service.orders_api, 'monthly_units', lambda *a, **k: _rows(24, pattern))
    r = client.get(f'/api/staff/forecast/{product_id}', headers=staff)
    assert r.status_code == 200
    body = r.json()
    assert len(body['history']) == 24
    assert body['candidate'] is not None and len(body['candidate']['forecast']) == 3
    assert body['evaluation']['available'] is True
    assert body['selectedModel'] in ('baseline', 'candidate')


def test_endpoint_no_history_via_empty_rows(client, staff, product_id, monkeypatch):
    monkeypatch.setattr(forecast_service.orders_api, 'monthly_units', lambda *a, **k: [])
    r = client.get(f'/api/staff/forecast/{product_id}', headers=staff)
    assert r.status_code == 422 and r.json()['error']['code'] == 'forecast_no_history'
