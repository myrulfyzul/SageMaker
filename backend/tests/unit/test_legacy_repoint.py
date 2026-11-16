"""Legacy module re-pointed at products/inventory/orders (Req 1.1, 1.2, 14.4, 22.13)."""
from __future__ import annotations

from app.db import connect

BODY = {'checkout_id': 'legacy-repoint-0001', 'customer_name': 'Demo Buyer', 'email': 'demo@example.com',
        'phone': '0123456789', 'delivery_address': '123 Sample Street, Sample City',
        'payment_method': 'demo_card', 'items': [{'product_id': 'fishing', 'quantity': 2}]}


def test_products_from_table_with_legacy_categories(client):
    items = client.get('/api/legacy/products').json()
    by_id = {p['id']: p for p in items}
    assert set(by_id) == {'fishing', 'hikayat', 'pouch', 'jendela'}
    assert by_id['fishing']['category'] == 'Kids & Toys' and by_id['jendela']['category'] == 'Bags'
    assert by_id['pouch']['category'] == 'Accessories' and by_id['fishing']['demoPriceSen'] == 3500


def test_guest_order_reserves_stock_and_follows_status_flow(client, settings):
    client.get('/api/legacy/products')
    res = client.post('/api/legacy/orders', json=BODY)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data['id'].startswith('DEMO-') and data['paymentStatus'] == 'demo_simulated_not_charged'
    assert data['items'][0] == {'productId': 'fishing', 'name': 'Fishing Mini Busy Book', 'quantity': 2,
                                'unitPriceSen': 3500, 'lineTotalSen': 7000}
    conn = connect(settings.database_path)
    try:
        order = conn.execute('SELECT user_id, source FROM orders WHERE id=?', (data['id'],)).fetchone()
        assert order['user_id'] is None and order['source'] == 'legacy'
        assert conn.execute("SELECT quantity FROM stock_levels WHERE sku_key='fishing'").fetchone()[0] == 98
    finally:
        conn.close()
    assert client.post('/api/legacy/orders', json=BODY).status_code == 409


def test_shortage_returns_409_and_creates_no_order(client, settings):
    client.get('/api/legacy/products')
    conn = connect(settings.database_path)
    conn.execute("UPDATE stock_levels SET quantity=1 WHERE sku_key='fishing'")
    conn.close()
    assert client.post('/api/legacy/orders', json=BODY).status_code == 409
    conn = connect(settings.database_path)
    try:
        assert conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 0
    finally:
        conn.close()
