"""Hosted-gateway checkout (Stripe sandbox): start a payment, confirm it, cancel it, handle the webhook.

The order is created only after the gateway reports the money as paid, by calling `service.place_order` with the
amount that was actually paid. If stock ran out or the cart changed in the meantime, the payment is refunded.
Confirmation can come from the signed webhook or from the app polling; both end up in `reconcile`, which is
safe to run twice because `place_order` is idempotent on the checkout key.
"""
from __future__ import annotations

import html
import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Optional

from app import db
from app.config import Settings
from app.errors import NotFound, ValidationFailed
from app.modules.cart import api as cart_api
from app.modules.inventory import api as inventory_api
from app.modules.orders import api as orders_api
from app.modules.payments import api as payments_api

from . import service
from .schemas import CheckoutIn, DeliveryIn, GatewayStartIn, validate_delivery, validate_idempotency_key

logger = logging.getLogger('sagemaker.gateway')

CHECKOUT_LIFETIME_SECONDS = 35 * 60  # Stripe requires at least 30 minutes
HANDLED_EVENTS = {
    'checkout.session.completed', 'checkout.session.async_payment_succeeded',
    'checkout.session.async_payment_failed', 'checkout.session.expired',
}


def _gateway(gateway: Any) -> Any:
    if gateway is None:
        raise payments_api.PaymentsNotConfigured('The payment gateway is not configured on this server.')
    return gateway


def public_view(session: dict[str, Any]) -> dict[str, Any]:
    """What the customer's app may see: no delivery details, no gateway ids."""
    return {'id': session['id'], 'status': session['status'], 'orderId': session['orderId'],
            'method': session['method'], 'provider': session['provider'], 'amountSen': session['amountSen'],
            'checkoutUrl': session['checkoutUrl'] if session['status'] == 'pending' else None,
            'message': session['failureReason'], 'createdAt': session['createdAt']}


def _check_provider(method: str, provider: Optional[str]) -> None:
    payments_api.validate_provider(method, provider)
    if method == 'ewallet' and provider not in (None, payments_api.GATEWAY_EWALLET):
        raise ValidationFailed([{'field': 'provider',
                                 'reason': f'only {payments_api.GATEWAY_EWALLET} is available through the gateway'}])


def _line_items(cart: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for ln in cart['lines']:
        name = ln['name'] + (f" ({ln['variationLabel']})" if ln.get('variationLabel') else '')
        items.append({'name': name, 'unit_amount_sen': ln['unitPriceSen'], 'quantity': ln['quantity']})
    if cart['deliveryFeeSen'] > 0:
        items.append({'name': 'Delivery', 'unit_amount_sen': cart['deliveryFeeSen'], 'quantity': 1})
    charged = sum(i['unit_amount_sen'] * i['quantity'] for i in items)
    if charged != cart['grandTotalSen']:  # an invariant of the server-priced cart; never send a wrong amount
        raise ValueError(f'line items add up to {charged}, cart total is {cart["grandTotalSen"]}')
    return items


def start(conn: sqlite3.Connection, settings: Settings, gateway: Any, user_id: int,
          body: GatewayStartIn) -> dict[str, Any]:
    """Create (or return the existing) pending payment session for the user's current cart."""
    gateway = _gateway(gateway)
    key = validate_idempotency_key(body.idempotency_key)
    delivery = validate_delivery(body.delivery)
    _check_provider(body.method, body.provider)

    existing = payments_api.find_session_by_key(conn, user_id, key)
    if existing is not None:
        return public_view(reconcile(conn, settings, gateway, existing))

    cart = cart_api.load_lines(conn, user_id)
    service.ensure_cart_ready(cart)
    total = cart['grandTotalSen']
    if body.method == 'fpx' and not payments_api.FPX_MIN_SEN <= total <= payments_api.FPX_MAX_SEN:
        raise ValidationFailed([{'field': 'method', 'reason': 'FPX accepts RM 1.00 to RM 30,000.00 per payment'}])
    if not settings.public_base_url:
        raise payments_api.GatewayUnavailable('PUBLIC_BASE_URL is not set, so the gateway cannot return to the app.')

    session_id = payments_api.new_session_id()
    base = f'{settings.public_base_url}/api/payments/return?s={session_id}'
    try:
        remote = gateway.create_checkout_session(
            line_items=_line_items(cart), method=body.method, success_url=base, cancel_url=f'{base}&cancelled=1',
            customer_email=delivery['email'], reference=session_id,
            expires_at=int(time.time()) + CHECKOUT_LIFETIME_SECONDS)
    except payments_api.GatewayError as exc:
        logger.warning('checkout session create failed for user %s: %s', user_id, exc.message)
        raise payments_api.GatewayUnavailable(exc.message) from exc

    try:
        with db.transaction(conn):
            row = payments_api.create_session(
                conn, session_id=session_id, user_id=user_id, idempotency_key=key, gateway='stripe',
                gateway_session_id=remote['id'], checkout_url=remote['url'], method=body.method,
                provider=body.provider, amount_sen=total, delivery=delivery)
    except sqlite3.IntegrityError:  # the same key was submitted twice at once
        row = payments_api.find_session_by_key(conn, user_id, key)
        if row is None:
            raise
    return public_view(row)


def _refund_and_close(gateway: Any, conn: sqlite3.Connection, session: dict[str, Any],
                      payment_intent: Optional[str], reason: str) -> dict[str, Any]:
    """Give the money back and close the session as `refunded`. If the refund itself fails the session is closed
    as `failed` with a note, so it shows up for manual follow-up instead of looking settled."""
    status, note = 'refunded', reason
    try:
        if not payment_intent:
            raise payments_api.GatewayError('no payment intent to refund')
        gateway.refund(payment_intent, session['id'])
    except payments_api.GatewayError as exc:
        logger.error('REFUND NEEDED for payment session %s (%s): %s', session['id'], reason, exc.message)
        status, note = 'failed', f'{reason}. Automatic refund failed, contact support with reference {session["id"]}.'
    with db.transaction(conn):
        payments_api.finish_session(conn, session['id'], status, reason=note)
    return payments_api.get_session(conn, session['id'])  # type: ignore[return-value]


def _fulfil(conn: sqlite3.Connection, gateway: Any, session: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
    intent = remote.get('payment_intent')
    payment_intent = intent.get('id') if isinstance(intent, dict) else intent
    if remote.get('amount_total') != session['amountSen'] or str(remote.get('currency', '')).lower() != 'myr':
        return _refund_and_close(gateway, conn, session, payment_intent, 'The amount paid did not match the order')
    body = CheckoutIn(idempotency_key=session['idempotencyKey'], delivery=DeliveryIn(**session['delivery']),
                      method=session['method'], outcome='success', provider=session['provider'])
    try:
        order, _ = service.place_order(conn, session['userId'], body, expected_total_sen=session['amountSen'],
                                       reference=payment_intent)
    except service.CartChanged:
        return _refund_and_close(gateway, conn, session, payment_intent,
                                 'Your cart changed while you were paying, so the payment was refunded')
    except (service.EmptyCart, inventory_api.InsufficientStock):
        return _refund_and_close(gateway, conn, session, payment_intent,
                                 'Some items sold out while you were paying, so the payment was refunded')
    with db.transaction(conn):
        payments_api.finish_session(conn, session['id'], 'paid', order_id=order['id'])
    return payments_api.get_session(conn, session['id'])  # type: ignore[return-value]


def reconcile(conn: sqlite3.Connection, settings: Settings, gateway: Any, session: dict[str, Any]) -> dict[str, Any]:
    """Bring a pending session up to date with the gateway. Final sessions are returned unchanged. A gateway
    outage leaves the session pending so the next poll or webhook can finish it."""
    if session['status'] != 'pending':
        return session
    gateway = _gateway(gateway)
    already = orders_api.find_by_idempotency_key(conn, session['userId'], session['idempotencyKey'])
    if already is not None:  # paid and ordered earlier; only the session row was not closed
        with db.transaction(conn):
            payments_api.finish_session(conn, session['id'], 'paid', order_id=already['id'])
        return payments_api.get_session(conn, session['id'])  # type: ignore[return-value]
    try:
        remote = gateway.retrieve_session(session['gatewaySessionId'])
    except payments_api.GatewayError as exc:
        logger.warning('could not read payment session %s: %s', session['id'], exc.message)
        return session
    if remote.get('payment_status') == 'paid':
        return _fulfil(conn, gateway, session, remote)
    if remote.get('status') == 'expired':
        with db.transaction(conn):
            payments_api.finish_session(conn, session['id'], 'expired',
                                        reason='The payment page expired before payment was made')
        return payments_api.get_session(conn, session['id'])  # type: ignore[return-value]
    return session


def get_for_user(conn: sqlite3.Connection, settings: Settings, gateway: Any, user_id: int,
                 session_id: str) -> dict[str, Any]:
    session = payments_api.get_session(conn, session_id)
    if session is None or session['userId'] != user_id:  # foreign and missing look the same
        raise NotFound()
    return public_view(reconcile(conn, settings, gateway, session))


def cancel(conn: sqlite3.Connection, settings: Settings, gateway: Any, user_id: int,
           session_id: str) -> dict[str, Any]:
    """Customer gave up. If the payment went through meanwhile, the order is kept."""
    gateway = _gateway(gateway)
    session = payments_api.get_session(conn, session_id)
    if session is None or session['userId'] != user_id:
        raise NotFound()
    session = reconcile(conn, settings, gateway, session)
    if session['status'] != 'pending':
        return public_view(session)
    try:
        gateway.expire_session(session['gatewaySessionId'])
    except payments_api.GatewayError:
        session = reconcile(conn, settings, gateway, session)  # it may have been paid a moment ago
        if session['status'] != 'pending':
            return public_view(session)
    with db.transaction(conn):
        payments_api.finish_session(conn, session['id'], 'cancelled', reason='You cancelled the payment')
    return public_view(payments_api.get_session(conn, session['id']))  # type: ignore[arg-type]


def handle_webhook(conn: sqlite3.Connection, settings: Settings, gateway: Any, event: dict[str, Any]) -> bool:
    """Process a verified Stripe event. True when it concerned one of our sessions."""
    if event.get('type') not in HANDLED_EVENTS:
        return False
    obj = (event.get('data') or {}).get('object') or {}
    gateway_session_id = obj.get('id')
    if not isinstance(gateway_session_id, str):
        return False
    session = payments_api.find_session_by_gateway_id(conn, gateway_session_id)
    if session is None:
        return False
    reconcile(conn, settings, gateway, session)  # re-reads the session from Stripe rather than trusting the body
    return True


# --- the page Stripe sends the customer back to -------------------------------------------------------------

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SageMaker payment</title>{refresh}
<style>body{{font-family:system-ui,sans-serif;background:#faf6ef;color:#1d2a25;margin:0;display:flex;
min-height:100vh;align-items:center;justify-content:center}}main{{background:#fff;max-width:420px;margin:16px;
padding:28px;border-radius:20px;box-shadow:0 10px 30px rgba(14,59,46,.12);text-align:center}}
.badge{{width:72px;height:72px;border-radius:50%;margin:0 auto 12px;display:flex;align-items:center;
justify-content:center;font-size:36px;color:#fff;background:{color}}}h1{{font-size:22px;margin:8px 0}}
p{{color:#5e6b66;line-height:1.5}}dl{{text-align:left;font-size:14px;margin:18px 0 0}}dt{{color:#5e6b66;
margin-top:8px}}dd{{margin:0;font-weight:600}}</style></head><body><main><div class="badge">{icon}</div>
<h1>{title}</h1><p>{message}</p>{details}<p style="margin-top:20px">You can close this page and go back to the
SageMaker app.</p></main></body></html>"""

_COPY = {
    'paid': ('Payment received', '#2e7d5b', '&#10003;', 'Thank you. Your order is confirmed.'),
    'pending': ('Confirming your payment', '#b7791f', '&#8987;', 'This page refreshes by itself.'),
    'cancelled': ('Payment cancelled', '#5e6b66', '&#10005;', 'No money was taken.'),
    'expired': ('Payment expired', '#5e6b66', '&#10005;', 'The payment page timed out. No money was taken.'),
    'failed': ('Payment problem', '#b3261e', '!', 'Something went wrong.'),
    'refunded': ('Payment refunded', '#b7791f', '&#8617;', 'Your money is being returned.'),
}


def _fpx_details(gateway: Any, session: dict[str, Any]) -> list[tuple[str, str]]:
    """Transaction details FPX requires the confirmation page to show (bank, FPX id), when Stripe provides them."""
    if session['method'] != 'fpx':
        return []
    try:
        remote = gateway.retrieve_session(session['gatewaySessionId'], expand=['payment_intent.latest_charge'])
        charge = ((remote.get('payment_intent') or {}).get('latest_charge') or {})
        fpx = (charge.get('payment_method_details') or {}).get('fpx') or {}
    except (payments_api.GatewayError, AttributeError):
        return []
    rows = []
    if fpx.get('bank'):
        rows.append(('Buyer bank', str(fpx['bank']).replace('_', ' ').title()))
    if fpx.get('transaction_id'):
        rows.append(('FPX transaction ID', str(fpx['transaction_id'])))
    return rows


def return_page(conn: sqlite3.Connection, settings: Settings, gateway: Any, session_id: str,
                cancelled: bool = False) -> tuple[int, str]:
    """HTML for Stripe's success and cancel URLs. Only reveals what the (unguessable) session id already proves."""
    session = payments_api.get_session(conn, session_id)
    if session is None:
        return 404, _PAGE.format(refresh='', color='#5e6b66', icon='?', title='Payment not found',
                                 message='This payment link is not valid.', details='')
    if gateway is not None:
        session = reconcile(conn, settings, gateway, session)
    status = session['status']
    if cancelled and status == 'pending':
        status = 'cancelled'
    title, color, icon, message = _COPY.get(status, _COPY['failed'])
    if session['failureReason'] and status in ('refunded', 'failed', 'expired'):
        message = session['failureReason']
    rows: list[tuple[str, str]] = [('Amount', f'RM {session["amountSen"] / 100:,.2f}')]
    if session['orderId']:
        rows.append(('Order', session['orderId']))
    rows.append(('Date', datetime.now(timezone.utc).astimezone().strftime('%d %b %Y, %H:%M')))
    if status == 'paid' and gateway is not None:
        rows.extend(_fpx_details(gateway, session))
    details = '<dl>' + ''.join(f'<dt>{html.escape(k)}</dt><dd>{html.escape(v)}</dd>' for k, v in rows) + '</dl>'
    refresh = '<meta http-equiv="refresh" content="3">' if status == 'pending' else ''
    return 200, _PAGE.format(refresh=refresh, color=color, icon=icon, title=html.escape(title),
                             message=html.escape(message), details=details)
