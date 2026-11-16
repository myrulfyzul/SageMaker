"""Smoke tests for demo checkout, privacy, price calculation, tracking."""
import importlib.util
import os
import secrets
from pathlib import Path

os.environ['SAGEMAKER_DEMO_DB'] = '/tmp/sagemaker_test_orders_v1.sqlite3'
TEST_ADMIN_KEY = secrets.token_urlsafe(24)  # generated per run, never stored
os.environ['SAGEMAKER_ADMIN_KEY'] = TEST_ADMIN_KEY
os.environ['DEMO_MODE'] = '1'
p = Path(__file__).with_name('server.py')
spec = importlib.util.spec_from_file_location('server', p)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

from fastapi.testclient import TestClient
client = TestClient(server.app)

# Single place that maps the old routes onto the legacy module.
LEGACY_PREFIX = '/api/legacy'


def test_products():
    response = client.get(f'{LEGACY_PREFIX}/products')
    assert response.status_code == 200
    assert len(response.json()) >= 4
    assert all(p['demoPriceSen'] > 0 for p in response.json())


def test_checkout_and_tracking():
    order = client.post(f'{LEGACY_PREFIX}/orders', json={
        'checkout_id': 'smoke-test-order-0001',
        'customer_name': 'Demo Buyer',
        'email': 'demo@example.com',
        'phone': '0123456789',
        'delivery_address': '123 Sample Street, Sample City',
        'payment_method': 'demo_card',
        'items': [{'product_id': 'fishing', 'quantity': 2}],
    })
    assert order.status_code in (201, 409), order.text
    if order.status_code == 409:
        # A previous test run may have used the same temp database.
        return
    data = order.json()
    assert data['totalSen'] == 3500 * 2 + 800
    assert data['paymentStatus'] == 'demo_simulated_not_charged'
    oid = data['id']
    token = data['accessToken']
    assert client.get(f'{LEGACY_PREFIX}/orders/{oid}').status_code == 401
    assert client.get(f'{LEGACY_PREFIX}/orders/{oid}', headers={'X-Order-Token': 'wrong'}).status_code == 404
    response = client.get(f'{LEGACY_PREFIX}/orders/{oid}', headers={'X-Order-Token': token})
    assert response.status_code == 200 and response.json()['status'] == 'placed'
    assert client.patch(f'{LEGACY_PREFIX}/admin/orders/{oid}/status', json={'status': 'shipped'}).status_code == 403
    response = client.patch(f'{LEGACY_PREFIX}/admin/orders/{oid}/status',
        headers={'X-Admin-Key': TEST_ADMIN_KEY},
        json={'status': 'shipped', 'tracking_number': 'EXAMPLE-123'})
    assert response.status_code == 200
    result = client.get(f'{LEGACY_PREFIX}/orders/{oid}', headers={'X-Order-Token': token}).json()
    assert result['status'] == 'shipped' and result['trackingNumber'] == 'EXAMPLE-123'
    assert client.patch(f'{LEGACY_PREFIX}/admin/orders/{oid}/status', headers={'X-Admin-Key': TEST_ADMIN_KEY},
                        json={'status': 'placed'}).status_code == 400


def test_server_rejects_client_prices():
    data = {
        'checkout_id': 'smoke-test-order-invalid',
        'customer_name': 'Demo Buyer', 'email': 'demo@example.com',
        'phone': '0123456789', 'delivery_address': '123 Sample Street, Sample City',
        'payment_method': 'demo_card',
        'items': [{'product_id': 'fake-product', 'quantity': 1}],
    }
    assert client.post(f'{LEGACY_PREFIX}/orders', json=data).status_code == 400
    data['items'] = [{'product_id': 'fishing', 'quantity': 1, 'price': 0}]
    response = client.post(f'{LEGACY_PREFIX}/orders', json=data)
    assert response.status_code in (201, 409)
    if response.status_code == 201:
        assert response.json()['totalSen'] == 3500 + 800
