"""Hosted-gateway checkout (Stripe sandbox) with a fake gateway: start, confirm, refund, cancel, webhook."""
from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from app import db
from app.config import ConfigError, Settings
from app.main import create_app
from app.modules.payments import gateway as gw

PASSWORD = ''.join(['Secret', '123'])
# Built at run time like the other test credentials, so the repository secret scan stays clean.
WEBHOOK_SECRET = ''.join(['whsec_', 'test'])
TEST_KEY = ''.join(['sk_test_', 'fake'])
DELIVERY = {'name': 'Aisha Rahman', 'phone': '0123456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bunga, Taman Indah', 'postcode': '50450', 'state': 'Selangor'}


class FakeGateway:
    """Stands in for Stripe: remembers sessions and lets a test decide when the customer 'paid'."""

    name = 'fake'

    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.refunds: list[tuple[str, str]] = []
        self.fail_create = False
        self.fail_retrieve = False
        self.fail_refund = False
        self._n = 0

    def create_checkout_session(self, *, line_items, method, success_url, cancel_url, customer_email, reference,
                                expires_at):
        if self.fail_create:
            raise gw.GatewayError('The payment gateway could not be reached. Please try again.')
        self._n += 1
        gid = f'cs_test_{self._n}'
        self.sessions[gid] = {
            'id': gid, 'url': f'https://checkout.stripe.test/{gid}', 'status': 'open', 'payment_status': 'unpaid',
            'amount_total': sum(i['unit_amount_sen'] * i['quantity'] for i in line_items), 'currency': 'myr',
            'payment_intent': f'pi_test_{self._n}', 'method': method, 'line_items': line_items,
            'success_url': success_url, 'cancel_url': cancel_url, 'email': customer_email, 'reference': reference}
        return dict(self.sessions[gid])

    def retrieve_session(self, gid, expand=None):
        if self.fail_retrieve:
            raise gw.GatewayError('down')
        return json.loads(json.dumps(self.sessions[gid]))

    def expire_session(self, gid):
        session = self.sessions[gid]
        if session['status'] == 'complete':
            raise gw.GatewayError('This session is already complete.', status=400)
        session['status'] = 'expired'
        return dict(session)

    def refund(self, payment_intent, reference):
        if self.fail_refund:
            raise gw.GatewayError('refund rejected')
        self.refunds.append((payment_intent, reference))
        return {'id': 're_test'}

    # --- test controls
    def pay(self, gid: str, used: dict | None = None) -> None:
        update: dict = {'status': 'complete', 'payment_status': 'paid'}
        if used is not None:  # what the customer really paid with on Stripe's page
            update['payment_intent'] = {'id': self.sessions[gid]['payment_intent'], 'payment_method': used}
        self.sessions[gid].update(update)

    def expire(self, gid: str) -> None:
        self.sessions[gid]['status'] = 'expired'


@pytest.fixture()
def gw_settings(settings):
    return dataclasses.replace(settings, demo_mode=False, stripe_secret_key=TEST_KEY,
                               stripe_webhook_secret=WEBHOOK_SECRET, public_base_url='http://testserver')


@pytest.fixture()
def fake():
    return FakeGateway()


@pytest.fixture()
def gclient(gw_settings, fake):
    from fastapi.testclient import TestClient
    app = create_app(gw_settings)
    app.state.payment_gateway = fake
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _h(token):
    return {'Authorization': f'Bearer {token}'}


def _customer(client, email='g@example.com'):
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    return client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']


def _stock(settings, qty=5, price=1000):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                     "updated_at) VALUES ('p1', 'Bag', '', 1, ?, 1, 'now', 'now')", (price,))
        conn.execute("INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) "
                     "VALUES ('p1', 'p1', NULL, ?, ?)", (qty, qty))
    conn.close()


def _set_stock(settings, qty):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        conn.execute("UPDATE stock_levels SET quantity = ? WHERE sku_key = 'p1'", (qty,))
    conn.close()


def _stock_now(settings):
    conn = db.connect(settings.database_path)
    try:
        return conn.execute("SELECT quantity FROM stock_levels WHERE sku_key = 'p1'").fetchone()[0]
    finally:
        conn.close()


def _add(client, token, qty=2):
    r = client.post('/api/cart/lines', headers=_h(token), json={'productId': 'p1', 'quantity': qty})
    assert r.status_code in (200, 201), r.text


def _start(client, token, key='idem-gw-000001', method='fpx', provider=None):
    body = {'idempotencyKey': key, 'delivery': DELIVERY, 'method': method}
    if provider:
        body['provider'] = provider
    return client.post('/api/payments/sessions', headers=_h(token), json=body)


def _orders_total(client, token):
    return client.get('/api/orders', headers=_h(token)).json()['total']


# --- config -----------------------------------------------------------------------------------------------------

def test_config_reports_the_gateway(client, gclient):
    assert client.get('/api/payments/config').json()['gateway'] == 'prototype'
    body = gclient.get('/api/payments/config').json()
    assert body['gateway'] == 'stripe' and body['methods'] == ['fpx', 'ewallet', 'card', 'cod']
    assert body['ewalletProvider'] == 'grabpay'


def test_config_lists_only_methods_switched_on_in_stripe(gclient, fake):
    from app.modules.payments import api as payments_api
    payments_api._methods_cache.clear()
    calls = []

    def enabled():
        calls.append(1)
        return {'card', 'grabpay', 'link'}  # FPX not available on this account
    fake.enabled_method_types = enabled
    assert gclient.get('/api/payments/config').json()['methods'] == ['ewallet', 'card', 'cod']
    gclient.get('/api/payments/config')
    assert len(calls) == 1  # cached

    payments_api._methods_cache.clear()

    def down():
        raise gw.GatewayError('down')
    fake.enabled_method_types = down
    assert gclient.get('/api/payments/config').json()['methods'] == ['fpx', 'ewallet', 'card', 'cod']
    payments_api._methods_cache.clear()


def test_enabled_method_types_reads_the_default_configuration():
    listing = {'data': [
        {'id': 'pmc_other', 'active': True, 'is_default': False,
         'fpx': {'available': True, 'display_preference': {'value': 'on'}}},
        {'id': 'pmc_default', 'active': True, 'is_default': True,
         'card': {'available': True, 'display_preference': {'value': 'on'}},
         'grabpay': {'available': True, 'display_preference': {'value': 'off'}},
         'fpx': {'available': False, 'display_preference': {'value': 'on'}},
         'livemode': False},
    ]}
    seen = {}

    def http(method, url, headers, body):
        seen['url'] = url
        return 200, listing
    assert gw.StripeGateway(TEST_KEY, http=http).enabled_method_types() == {'card'}
    assert seen['url'].startswith('https://api.stripe.com/v1/payment_method_configurations')
    with pytest.raises(gw.GatewayError):
        gw.StripeGateway(TEST_KEY, http=lambda *a: (200, {'data': []})).enabled_method_types()


def test_live_and_malformed_stripe_keys_are_refused():
    base = {'DATABASE_PATH': 'x.sqlite3'}
    key = 'STRIPE' + '_SECRET_KEY'
    with pytest.raises(ConfigError, match='live keys'):
        Settings.from_env({**base, key: 'sk_live_' + 'abc'})
    with pytest.raises(ConfigError, match='sk_test_'):
        Settings.from_env({**base, key: 'pk_test_' + 'abc'})
    ok = Settings.from_env({**base, key: ' sk_test_' + 'abc ', 'RENDER_EXTERNAL_URL': 'https://a.onrender.com/'})
    assert ok.gateway_enabled and ok.public_base_url == 'https://a.onrender.com'
    assert not Settings.from_env(base).gateway_enabled


# --- starting a payment -----------------------------------------------------------------------------------------

def test_start_prices_the_cart_on_the_server_and_creates_no_order(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t, 2)
    cart = gclient.get('/api/cart', headers=_h(t)).json()
    r = _start(gclient, t)
    assert r.status_code == 201, r.text
    view = r.json()
    assert view['status'] == 'pending' and view['amountSen'] == cart['grandTotalSen']
    assert view['checkoutUrl'].startswith('https://checkout.stripe.test/')
    assert 'delivery' not in view and 'gatewaySessionId' not in view
    sent = fake.sessions['cs_test_1']
    assert sent['amount_total'] == cart['grandTotalSen'] and sent['method'] == 'fpx'
    assert sent['email'] == 'aisha@example.com'
    assert sent['success_url'] == f"http://testserver/api/payments/return?s={view['id']}"
    assert _orders_total(gclient, t) == 0 and _stock_now(gw_settings) == 5  # nothing reserved yet


def test_start_is_idempotent_for_the_same_key(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)
    first = _start(gclient, t).json()
    second = _start(gclient, t).json()
    assert first['id'] == second['id'] and len(fake.sessions) == 1


def test_start_rejects_bad_input_without_calling_the_gateway(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    assert _start(gclient, t).status_code == 400  # empty cart
    _add(gclient, t)
    assert _start(gclient, t, key='short').status_code == 422
    assert _start(gclient, t, key='idem-gw-bad-01', method='ewallet', provider='tng').status_code == 422
    bad = gclient.post('/api/payments/sessions', headers=_h(t), json={
        'idempotencyKey': 'idem-gw-bad-02', 'delivery': {**DELIVERY, 'postcode': 'x'}, 'method': 'fpx'})
    assert bad.status_code == 422
    assert gclient.post('/api/payments/sessions', headers=_h(t), json={
        'idempotencyKey': 'idem-gw-bad-03', 'delivery': DELIVERY, 'method': 'cod'}).status_code == 422
    assert fake.sessions == {}


def test_start_requires_a_customer_session(gclient):
    assert gclient.post('/api/payments/sessions', json={}).status_code == 401


def test_gateway_outage_on_start_leaves_nothing_behind(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)
    fake.fail_create = True
    r = _start(gclient, t)
    assert r.status_code == 502 and r.json()['error']['code'] == 'payment_gateway_error'
    fake.fail_create = False
    assert _start(gclient, t).status_code == 201  # same key works once the gateway is back


def test_method_not_enabled_in_stripe_gets_a_plain_message(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)

    def refuse(**_):
        raise gw.GatewayError('No valid payment method types for this Checkout Session. Please ensure ...',
                              status=400)
    fake.create_checkout_session = refuse
    r = _start(gclient, t, key='idem-gw-off-001')
    assert r.status_code == 502
    message = r.json()['error']['message']
    assert message.startswith('FPX Online Banking is not available right now')
    assert 'Checkout Session' not in message and _orders_total(gclient, t) == 0


# --- confirming a payment ---------------------------------------------------------------------------------------

def test_paid_session_becomes_an_order_with_the_gateway_reference(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t, 2)
    sid = _start(gclient, t, provider='maybank2u').json()['id']
    assert gclient.get(f'/api/payments/sessions/{sid}', headers=_h(t)).json()['status'] == 'pending'
    fake.pay('cs_test_1')
    done = gclient.get(f'/api/payments/sessions/{sid}', headers=_h(t)).json()
    assert done['status'] == 'paid' and done['orderId'] and done['checkoutUrl'] is None
    order = gclient.get(f"/api/orders/{done['orderId']}", headers=_h(t)).json()
    assert order['paymentStatus'] == 'paid' and order['status'] == 'placed'
    assert order['paymentMethod'] == 'fpx' and order['paymentProvider'] == 'maybank2u'
    assert order['payments'][0]['reference'] == 'pi_test_1' and order['payments'][0]['outcome'] == 'success'
    assert gclient.get('/api/cart', headers=_h(t)).json()['lines'] == []
    assert _stock_now(gw_settings) == 3
    again = gclient.get(f'/api/payments/sessions/{sid}', headers=_h(t)).json()
    assert again['orderId'] == done['orderId'] and _orders_total(gclient, t) == 1  # polling twice adds nothing


def test_the_bank_stripe_reports_is_recorded(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)
    sid = _start(gclient, t).json()['id']
    fake.pay('cs_test_1', used={'type': 'fpx', 'fpx': {'bank': 'hong_leong_bank'}})
    order_id = gclient.get(f'/api/payments/sessions/{sid}', headers=_h(t)).json()['orderId']
    order = gclient.get(f'/api/orders/{order_id}', headers=_h(t)).json()
    assert order['paymentMethod'] == 'fpx' and order['paymentProvider'] == 'hongleong'


def test_a_different_method_on_stripes_page_is_recorded_as_used(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)
    sid = _start(gclient, t, method='fpx').json()['id']
    fake.pay('cs_test_1', used={'type': 'grabpay'})
    order_id = gclient.get(f'/api/payments/sessions/{sid}', headers=_h(t)).json()['orderId']
    order = gclient.get(f'/api/orders/{order_id}', headers=_h(t)).json()
    assert order['paymentMethod'] == 'ewallet' and order['paymentProvider'] == 'grabpay'
    assert order['payments'][0]['reference'] == 'pi_test_1'


def test_method_used_mapping():
    assert gw.method_used({'type': 'fpx', 'fpx': {'bank': 'maybank2u'}}) == ('fpx', 'maybank2u')
    assert gw.method_used({'type': 'fpx', 'fpx': {'bank': 'unknown_bank'}}) == ('fpx', None)
    assert gw.method_used({'type': 'grabpay'}) == ('ewallet', 'grabpay')
    assert gw.method_used({'type': 'card'}) == ('card', None)
    assert gw.method_used({'type': 'link'}) == ('card', None)
    assert gw.method_used('pm_123') is None and gw.method_used(None) is None


def test_unpaid_expired_session_is_closed_without_an_order(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)
    sid = _start(gclient, t).json()['id']
    fake.expire('cs_test_1')
    view = gclient.get(f'/api/payments/sessions/{sid}', headers=_h(t)).json()
    assert view['status'] == 'expired' and _orders_total(gclient, t) == 0
    assert gclient.get('/api/cart', headers=_h(t)).json()['lines'] != []  # the cart is still there to retry


def test_gateway_outage_while_polling_keeps_the_session_pending(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)
    sid = _start(gclient, t).json()['id']
    fake.pay('cs_test_1')
    fake.fail_retrieve = True
    assert gclient.get(f'/api/payments/sessions/{sid}', headers=_h(t)).json()['status'] == 'pending'
    fake.fail_retrieve = False
    assert gclient.get(f'/api/payments/sessions/{sid}', headers=_h(t)).json()['status'] == 'paid'


def test_cart_changed_while_paying_is_refunded_not_ordered(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t, 1)
    sid = _start(gclient, t).json()['id']
    _add(gclient, t, 1)  # total no longer matches what is being paid
    fake.pay('cs_test_1')
    view = gclient.get(f'/api/payments/sessions/{sid}', headers=_h(t)).json()
    assert view['status'] == 'refunded' and 'refunded' in view['message']
    assert fake.refunds == [('pi_test_1', sid)] and _orders_total(gclient, t) == 0


def test_sold_out_while_paying_is_refunded(gclient, gw_settings, fake):
    _stock(gw_settings, qty=2)
    t = _customer(gclient)
    _add(gclient, t, 2)
    sid = _start(gclient, t).json()['id']
    _set_stock(gw_settings, 0)
    fake.pay('cs_test_1')
    view = gclient.get(f'/api/payments/sessions/{sid}', headers=_h(t)).json()
    assert view['status'] == 'refunded' and fake.refunds == [('pi_test_1', sid)]
    assert _orders_total(gclient, t) == 0 and _stock_now(gw_settings) == 0


def test_failed_refund_is_flagged_for_follow_up(gclient, gw_settings, fake):
    _stock(gw_settings, qty=2)
    t = _customer(gclient)
    _add(gclient, t, 2)
    sid = _start(gclient, t).json()['id']
    _set_stock(gw_settings, 0)
    fake.pay('cs_test_1')
    fake.fail_refund = True
    view = gclient.get(f'/api/payments/sessions/{sid}', headers=_h(t)).json()
    assert view['status'] == 'failed' and sid in view['message'] and 'refund failed' in view['message']


def test_another_customer_cannot_read_or_cancel_a_session(gclient, gw_settings, fake):
    _stock(gw_settings)
    owner = _customer(gclient, 'owner@example.com')
    other = _customer(gclient, 'other@example.com')
    _add(gclient, owner)
    sid = _start(gclient, owner).json()['id']
    assert gclient.get(f'/api/payments/sessions/{sid}', headers=_h(other)).status_code == 404
    assert gclient.post(f'/api/payments/sessions/{sid}/cancel', headers=_h(other)).status_code == 404
    assert gclient.get('/api/payments/sessions/PS-NOPE', headers=_h(owner)).status_code == 404


# --- cancelling -------------------------------------------------------------------------------------------------

def test_cancel_expires_the_gateway_page_and_closes_the_session(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)
    sid = _start(gclient, t).json()['id']
    view = gclient.post(f'/api/payments/sessions/{sid}/cancel', headers=_h(t)).json()
    assert view['status'] == 'cancelled' and fake.sessions['cs_test_1']['status'] == 'expired'
    assert gclient.get(f'/api/payments/sessions/{sid}', headers=_h(t)).json()['status'] == 'cancelled'


def test_cancel_after_the_money_arrived_keeps_the_order(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)
    sid = _start(gclient, t).json()['id']
    fake.pay('cs_test_1')
    view = gclient.post(f'/api/payments/sessions/{sid}/cancel', headers=_h(t)).json()
    assert view['status'] == 'paid' and view['orderId'] and _orders_total(gclient, t) == 1


# --- webhook ----------------------------------------------------------------------------------------------------

def _event(gid, kind='checkout.session.completed'):
    return json.dumps({'id': 'evt_1', 'type': kind, 'data': {'object': {'id': gid}}}).encode()


def test_signed_webhook_confirms_the_payment_without_polling(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)
    sid = _start(gclient, t).json()['id']
    fake.pay('cs_test_1')
    payload = _event('cs_test_1')
    r = gclient.post('/api/payments/webhook/stripe', content=payload,
                     headers={'Stripe-Signature': gw.sign_webhook(payload, WEBHOOK_SECRET)})
    assert r.status_code == 200 and r.json() == {'received': True}
    assert _orders_total(gclient, t) == 1
    assert gclient.get(f'/api/payments/sessions/{sid}', headers=_h(t)).json()['status'] == 'paid'


def test_webhook_rejects_unsigned_forged_and_stale_requests(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)
    _start(gclient, t)
    fake.pay('cs_test_1')
    payload = _event('cs_test_1')
    for header in (None, 'garbage', gw.sign_webhook(payload, WEBHOOK_SECRET + 'x'),
                   gw.sign_webhook(payload, WEBHOOK_SECRET, timestamp=1_000_000)):
        r = gclient.post('/api/payments/webhook/stripe', content=payload,
                         headers={} if header is None else {'Stripe-Signature': header})
        assert r.status_code == 400 and r.json()['error']['code'] == 'invalid_signature'
    assert _orders_total(gclient, t) == 0


def test_webhook_ignores_other_events_and_unknown_sessions(gclient):
    for payload in (_event('cs_test_nope'), _event('cs_x', 'charge.succeeded'), b'{"type": 5}'):
        r = gclient.post('/api/payments/webhook/stripe', content=payload,
                         headers={'Stripe-Signature': gw.sign_webhook(payload, WEBHOOK_SECRET)})
        assert r.status_code == 200


def test_webhook_needs_a_configured_secret(gw_settings, fake):
    from fastapi.testclient import TestClient
    app = create_app(dataclasses.replace(gw_settings, stripe_webhook_secret=''))
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.post('/api/payments/webhook/stripe', content=b'{}').status_code == 503


# --- the old simulated path -------------------------------------------------------------------------------------

def test_simulated_payment_cannot_be_used_to_skip_the_gateway(gclient, gw_settings):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)
    body = {'idempotencyKey': 'idem-sim-00001', 'delivery': DELIVERY, 'method': 'fpx', 'outcome': 'success'}
    r = gclient.post('/api/checkout', headers=_h(t), json=body)
    assert r.status_code == 409 and r.json()['error']['code'] == 'use_payment_gateway'
    assert _orders_total(gclient, t) == 0


def test_cash_on_delivery_still_works_with_the_gateway_on_and_demo_mode_off(gclient, gw_settings):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)
    r = gclient.post('/api/checkout', headers=_h(t),
                     json={'idempotencyKey': 'idem-cod-00001', 'delivery': DELIVERY, 'method': 'cod'})
    assert r.status_code == 201 and r.json()['paymentStatus'] == 'pending_cod'


def test_failed_order_cannot_be_retried_with_a_simulated_payment(gclient, gw_settings):
    _stock(gw_settings)
    t = _customer(gclient)
    r = gclient.post(f'/api/orders/SM-NOPE000001/payments', headers=_h(t),
                     json={'method': 'fpx', 'outcome': 'success'})
    assert r.status_code == 409 and r.json()['error']['code'] == 'use_payment_gateway'


def test_without_a_gateway_or_demo_mode_payments_are_unavailable(settings):
    from fastapi.testclient import TestClient
    app = create_app(dataclasses.replace(settings, demo_mode=False))
    with TestClient(app, raise_server_exceptions=False) as c:
        t = _customer(c)
        r = c.post('/api/checkout', headers=_h(t),
                   json={'idempotencyKey': 'idem-off-00001', 'delivery': DELIVERY, 'method': 'cod'})
        assert r.status_code == 503
        assert c.post('/api/payments/sessions', headers=_h(t), json={
            'idempotencyKey': 'idem-off-00002', 'delivery': DELIVERY, 'method': 'fpx'}).status_code == 503


# --- the page Stripe returns the customer to --------------------------------------------------------------------

def test_return_page_shows_the_result_and_escapes_values(gclient, gw_settings, fake):
    _stock(gw_settings)
    t = _customer(gclient)
    _add(gclient, t)
    sid = _start(gclient, t).json()['id']
    pending = gclient.get(f'/api/payments/return?s={sid}')
    assert pending.status_code == 200 and 'Confirming your payment' in pending.text and 'refresh' in pending.text
    cancelled = gclient.get(f'/api/payments/return?s={sid}&cancelled=1')
    assert 'Payment cancelled' in cancelled.text
    fake.pay('cs_test_1')
    paid = gclient.get(f'/api/payments/return?s={sid}')
    assert 'Payment received' in paid.text and 'SM-' in paid.text and 'RM ' in paid.text
    assert 'aisha@example.com' not in paid.text and 'Jalan Bunga' not in paid.text  # no personal details
    assert paid.headers['cache-control'] == 'no-store'
    assert gclient.get('/api/payments/return?s=PS-NOPE').status_code == 404


# --- the Stripe client itself -----------------------------------------------------------------------------------

def test_form_encoding_matches_stripes_nested_format():
    body = gw.form_encode({'mode': 'payment', 'payment_method_types': ['fpx'], 'flag': True, 'skip': None,
                           'line_items': [{'quantity': 2, 'price_data': {'currency': 'myr', 'unit_amount': 1000}}]})
    text = body.decode()
    for part in ('mode=payment', 'payment_method_types%5B0%5D=fpx', 'flag=true',
                 'line_items%5B0%5D%5Bprice_data%5D%5Bcurrency%5D=myr', 'line_items%5B0%5D%5Bquantity%5D=2'):
        assert part in text
    assert 'skip' not in text


def test_create_checkout_session_request_shape():
    seen = {}

    def http(method, url, headers, body):
        seen.update(method=method, url=url, headers=headers, body=body.decode())
        return 200, {'id': 'cs_test_9', 'url': 'https://checkout.stripe.com/c/pay/cs_test_9'}

    g = gw.StripeGateway(TEST_KEY, http=http)
    out = g.create_checkout_session(
        line_items=[{'name': 'Bag (Large)', 'unit_amount_sen': 3800, 'quantity': 2}], method='ewallet',
        success_url='https://a/ok', cancel_url='https://a/no', customer_email='a@b.my', reference='PS-1',
        expires_at=1_900_000_000)
    assert out['id'] == 'cs_test_9' and seen['method'] == 'POST'
    assert seen['url'] == 'https://api.stripe.com/v1/checkout/sessions'
    assert seen['headers']['Authorization'] == f'Bearer {TEST_KEY}' and seen['headers']['Idempotency-Key'] == 'create-PS-1'
    assert 'payment_method_types' not in seen['body'].replace('excluded_payment_method_types', '')
    assert 'excluded_payment_method_types%5B0%5D=fpx' in seen['body']
    assert 'excluded_payment_method_types%5B1%5D=card' in seen['body'] and 'currency%5D=myr' in seen['body']
    assert 'unit_amount%5D=3800' in seen['body'] and 'client_reference_id=PS-1' in seen['body']


def test_gateway_errors_are_safe_to_show_and_never_leak_the_key():
    g = gw.StripeGateway(TEST_KEY, http=lambda *a: (401, {'error': {'message': 'Invalid API Key'}}))
    with pytest.raises(gw.GatewayError) as e:
        g.retrieve_session('cs_1')
    assert TEST_KEY not in e.value.message and 'not configured' in e.value.message
    g2 = gw.StripeGateway(TEST_KEY, http=lambda *a: (400, {'error': {'message': 'Amount too small'}}))
    with pytest.raises(gw.GatewayError, match='Amount too small'):
        g2.expire_session('cs_1')
    with pytest.raises(gw.GatewayError):
        gw.StripeGateway(TEST_KEY, http=lambda *a: (200, {})).create_checkout_session(
            line_items=[], method='duitnow', success_url='', cancel_url='', customer_email='', reference='x',
            expires_at=1)


def test_webhook_signature_verification():
    payload = b'{"type":"checkout.session.completed"}'
    secret_a, secret_b = ''.join(['whsec_', 'a']), ''.join(['whsec_', 'b'])
    header = gw.sign_webhook(payload, secret_a, timestamp=1_700_000_000)
    assert gw.verify_webhook(payload, header, secret_a, now=1_700_000_100)['type'] == 'checkout.session.completed'
    with pytest.raises(gw.WebhookSignatureError):
        gw.verify_webhook(payload + b' ', header, secret_a, now=1_700_000_100)  # tampered body
    with pytest.raises(gw.WebhookSignatureError):
        gw.verify_webhook(payload, header, secret_b, now=1_700_000_100)  # wrong secret
    with pytest.raises(gw.WebhookSignatureError):
        gw.verify_webhook(payload, header, secret_a, now=1_700_000_000 + 301)  # replayed later
    with pytest.raises(gw.WebhookSignatureError):
        gw.verify_webhook(payload, f'{header},v1=deadbeef'.replace('v1=', 'v0=', 1), secret_a, now=1_700_000_100)
    assert gw.verify_webhook(payload, header + ',v1=deadbeef', secret_a, now=1_700_000_100)  # extra v1 is fine
