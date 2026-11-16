"""End-to-end demo scenario through the HTTP API only (Req 30.1-30.9).

Steps 1 to 7 run in sequence against a temporary, seeded database. Each step runs through `_step`, which turns any
failure into an error naming the step; because the first failure aborts the test, no later step is executed.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import seed  # noqa: E402

CUSTOMER_PASSWORD = ''.join(['E2e', 'Customer', '1!'])
DELIVERY = {'name': 'Nur Aisyah', 'phone': '0123456789', 'email': 'e2e.customer@example.com',
            'address': '12 Jalan Bunga, Taman Indah', 'postcode': '50450', 'state': 'Selangor'}
QUANTITY = 2
SHIPPING_REF = 'MYPOST-E2E-0001'


class StepFailed(AssertionError):
    pass


@contextmanager
def _step(name):
    try:
        yield
    except StepFailed:
        raise
    except Exception as exc:  # noqa: BLE001 - any failure is reported with the step name
        raise StepFailed(f'Step failed: {name}: {type(exc).__name__}: {exc}') from exc


def _h(token):
    return {'Authorization': f'Bearer {token}'}


def _ok(response, *codes):
    assert response.status_code in (codes or (200,)), f'{response.request.method} {response.request.url} -> ' \
                                                      f'{response.status_code} {response.text}'
    return response.json() if response.content else None


def _login(client, email, password):
    return _ok(client.post('/api/auth/login', json={'email': email, 'password': password}))['token']


@pytest.fixture()
def seeded(settings):
    assert seed.main([], environ={'DATABASE_PATH': str(settings.database_path)}) == seed.EXIT_OK


def test_end_to_end_demo_scenario(seeded, client):
    ctx = {}

    # --- sign in (customer, staff, artisan) and baseline ------------------------------------------------------------
    with _step('0 setup: register and log in customer, staff and artisan'):
        _ok(client.post('/api/auth/register', json={'name': 'Nur Aisyah', 'email': DELIVERY['email'],
                                                    'password': CUSTOMER_PASSWORD}), 201)
        ctx['cust'] = _login(client, DELIVERY['email'], CUSTOMER_PASSWORD)
        ctx['staff'] = _login(client, 'demo.admin@example.com', 'DemoAdmin1!')
        ctx['artisan'] = _login(client, 'demo.artisan@example.com', 'DemoArtisan1!')
        assert _ok(client.get('/api/auth/session', headers=_h(ctx['cust'])))['user']['role'] == 'customer'
        dash = _ok(client.get('/api/staff/analytics/dashboard', headers=_h(ctx['staff'])))
        ctx['before'] = dash
        ctx['jobs_before'] = _ok(client.get('/api/production/jobs?limit=100', headers=_h(ctx['staff'])))['total']
        assert dash['bestSellers'], 'seeded data must provide best sellers'

    # --- Step 1: browse, cart, checkout -----------------------------------------------------------------------------
    with _step('1 browse products, add to cart and check out with a successful demo payment'):
        listing = _ok(client.get('/api/products?limit=100'))
        products = {p['id']: p for p in listing['items']}
        # Order the current top seller that is in stock: it stays in the top 5, so its increase is observable.
        pick = next(b for b in dash['bestSellers']
                    if b['productId'] in products and products[b['productId']]['stock']['quantity'] >= QUANTITY
                    and not products[b['productId']]['variations'])
        ctx['pid'] = pick['productId']
        ctx['units_before'] = pick['units']
        product = _ok(client.get(f'/api/products/{ctx["pid"]}'))
        stock_before = product['stock']['quantity']
        ctx['made_to_order'] = product['madeToOrder']

        cart = _ok(client.post('/api/cart/lines', headers=_h(ctx['cust']),
                               json={'productId': ctx['pid'], 'quantity': QUANTITY}))
        assert len(cart['lines']) == 1 and cart['lines'][0]['quantity'] == QUANTITY

        order = _ok(client.post('/api/checkout', headers=_h(ctx['cust']),
                                json={'idempotencyKey': 'e2e-checkout-0001', 'delivery': DELIVERY,
                                      'method': 'card', 'outcome': 'success'}), 201)
        ctx['order'] = order
        ctx['oid'] = order['id']
        assert order['paymentStatus'] == 'paid' and order['status'] == 'placed'
        assert [(ln['productId'], ln['quantity']) for ln in order['lines']] == [(ctx['pid'], QUANTITY)]

        mine = _ok(client.get('/api/orders', headers=_h(ctx['cust'])))
        assert [o['id'] for o in mine['items']] == [ctx['oid']], 'exactly one order'
        assert _ok(client.get('/api/cart', headers=_h(ctx['cust'])))['lines'] == [], 'cart must be empty'
        after = _ok(client.get(f'/api/products/{ctx["pid"]}'))
        assert after['stock']['quantity'] == stock_before - QUANTITY, 'stock must decrease by the ordered quantity'

    # --- Step 2: staff sees the same order --------------------------------------------------------------------------
    with _step('2 staff sees the same order'):
        listed = _ok(client.get('/api/staff/orders?limit=100', headers=_h(ctx['staff'])))
        row = next((o for o in listed['items'] if o['id'] == ctx['oid']), None)
        assert row is not None, 'order missing from staff list'
        assert row['totalSen'] == ctx['order']['totalSen'] and row['status'] == ctx['order']['status']
        assert [(ln['productId'], ln['quantity']) for ln in row['lines']] == [(ctx['pid'], QUANTITY)]
        detail = _ok(client.get(f'/api/staff/orders/{ctx["oid"]}', headers=_h(ctx['staff'])))
        assert detail['totalSen'] == ctx['order']['totalSen']

    # --- Step 3: confirm and assign a production job; artisan sees it -----------------------------------------------
    with _step('3 staff confirms the order and assigns a production job'):
        confirmed = _ok(client.post(f'/api/staff/orders/{ctx["oid"]}/status', headers=_h(ctx['staff']),
                                    json={'status': 'confirmed'}))
        assert confirmed['status'] == 'confirmed'
        jobs = _ok(client.get('/api/production/jobs?limit=100', headers=_h(ctx['staff'])))['items']
        mine = [j for j in jobs if j['orderId'] == ctx['oid']]
        if not mine:  # a stocked, non-made-to-order line gets no automatic job: staff creates it (Req 24.2)
            line_id = confirmed['lines'][0]['id']
            _ok(client.post('/api/production/jobs', headers=_h(ctx['staff']),
                            json={'orderId': ctx['oid'], 'orderLineId': line_id}), 201)
            jobs = _ok(client.get('/api/production/jobs?limit=100', headers=_h(ctx['staff'])))['items']
            mine = [j for j in jobs if j['orderId'] == ctx['oid']]
        assert len(mine) == 1, f'expected exactly one job for the order, got {len(mine)}'
        job = mine[0]
        # the Artisan profile linked to the demo Artisan_User owns the seeded jobs the artisan can already see
        own_jobs_before = _ok(client.get('/api/production/jobs?limit=100', headers=_h(ctx['artisan'])))['items']
        artisan_id = own_jobs_before[0]['artisanId']
        assigned = _ok(client.post(f'/api/production/jobs/{job["id"]}/assign', headers=_h(ctx['staff']),
                                   json={'artisanId': artisan_id, 'quantity': QUANTITY, 'deadline': '2999-12-31',
                                         'priority': 'normal', 'notes': 'e2e'}))
        assert assigned['artisanId'] == artisan_id and assigned['orderId'] == ctx['oid']
        ctx['job_id'] = job['id']
        visible = _ok(client.get('/api/production/jobs?limit=100', headers=_h(ctx['artisan'])))['items']
        assert ctx['job_id'] in [j['id'] for j in visible], 'job not visible to the Artisan_User'
        _ok(client.get(f'/api/production/jobs/{ctx["job_id"]}', headers=_h(ctx['artisan'])))

    # --- Step 4: progress visible on customer tracking --------------------------------------------------------------
    with _step('4 production progress shows on the customer tracking view'):
        _ok(client.post(f'/api/production/jobs/{ctx["job_id"]}/progress', headers=_h(ctx['staff']),
                        json={'percent': 60, 'note': 'half way'}))
        tracking = _ok(client.get(f'/api/orders/{ctx["oid"]}', headers=_h(ctx['cust'])))
        assert tracking['productionLabel'] == 'production_assigned'
        assert tracking['productionProgressPercent'] == 60, f'progress not on tracking view: {tracking}'

    # --- Step 5: preparing, shipped with reference -------------------------------------------------------------------
    with _step('5 staff ships the order with a shipping reference'):
        _ok(client.post(f'/api/staff/orders/{ctx["oid"]}/status', headers=_h(ctx['staff']),
                        json={'status': 'preparing'}))
        shipped = _ok(client.post(f'/api/staff/orders/{ctx["oid"]}/status', headers=_h(ctx['staff']),
                                  json={'status': 'shipped', 'shipping_reference': SHIPPING_REF}))
        assert shipped['status'] == 'shipped' and shipped['shippingReference'] == SHIPPING_REF
        tracking = _ok(client.get(f'/api/orders/{ctx["oid"]}', headers=_h(ctx['cust'])))
        assert tracking['status'] == 'shipped' and tracking['shippingReference'] == SHIPPING_REF
        assert [h['status'] for h in tracking['history']][-3:] == ['confirmed', 'preparing', 'shipped']

    # --- Step 6: dashboard KPIs ---------------------------------------------------------------------------------------
    total = ctx['order']['totalSen']
    with _step('6 dashboard KPIs include the shipped order'):
        now = _ok(client.get('/api/staff/analytics/dashboard', headers=_h(ctx['staff'])))
        k0, k1 = ctx['before']['kpis'], now['kpis']
        assert k1['totalRevenueSen'] == k0['totalRevenueSen'] + total
        assert k1['orderCount'] == k0['orderCount'] + 1
        assert k1['shippedOrderCount'] == k0['shippedOrderCount'] + 1

    # --- Step 7: best sellers / analytics ---------------------------------------------------------------------------
    with _step('7 best sellers and revenue include the new order'):
        top = {b['productId']: b['units'] for b in now['bestSellers']}
        assert top.get(ctx['pid']) == ctx['units_before'] + QUANTITY, f'best sellers: {now["bestSellers"]}'
        assert _ok(client.get('/api/staff/inventory/' + ctx['pid'], headers=_h(ctx['staff'])))
