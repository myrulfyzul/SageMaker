"""Stripe (sandbox) client and webhook verification, built on the standard library only.

Nothing here touches the database. `StripeGateway` takes an `http` callable so tests can run without a network;
the default sends the request with urllib. The secret key never appears in logs or error messages.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

API_BASE = 'https://api.stripe.com/v1'
REQUEST_TIMEOUT_SECONDS = 20
WEBHOOK_TOLERANCE_SECONDS = 300

# What Stripe's hosted Checkout can take in Malaysia. DuitNow QR, Touch 'n Go, Boost and ShopeePay are not offered.
STRIPE_METHOD_TYPES = {'fpx': 'fpx', 'ewallet': 'grabpay', 'card': 'card'}
GATEWAY_EWALLET = 'grabpay'

# (HTTP method, url, headers, body bytes or None) -> (status, parsed JSON body)
HttpCall = Callable[[str, str, dict[str, str], Optional[bytes]], tuple[int, dict[str, Any]]]


class GatewayError(Exception):
    """The gateway refused or could not complete a call. `message` is safe to show to a customer."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message = message
        self.status = status


class WebhookSignatureError(Exception):
    """The webhook body was not signed by Stripe, or the timestamp is outside the tolerance."""


def _flatten(prefix: str, value: Any, out: list[tuple[str, str]]) -> None:
    """Stripe's form encoding: nested dicts become a[b][c], lists become a[0]."""
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f'{prefix}[{k}]' if prefix else str(k), v, out)
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _flatten(f'{prefix}[{i}]', v, out)
    elif value is None:
        return
    elif isinstance(value, bool):
        out.append((prefix, 'true' if value else 'false'))
    else:
        out.append((prefix, str(value)))


def form_encode(data: dict[str, Any]) -> bytes:
    pairs: list[tuple[str, str]] = []
    _flatten('', data, pairs)
    return urllib.parse.urlencode(pairs).encode('utf-8')


def _urllib_http(method: str, url: str, headers: dict[str, str], body: Optional[bytes]) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.status, json.loads(response.read().decode('utf-8') or '{}')
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode('utf-8') or '{}')
        except ValueError:
            return exc.code, {}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GatewayError('The payment gateway could not be reached. Please try again.') from exc


class StripeGateway:
    """Minimal Stripe REST client for hosted Checkout in sandbox mode."""

    name = 'stripe'

    def __init__(self, secret_key: str, http: Optional[HttpCall] = None):
        self._key = secret_key
        self._http = http or _urllib_http

    def _call(self, method: str, path: str, data: Optional[dict[str, Any]] = None,
              idempotency_key: Optional[str] = None) -> dict[str, Any]:
        headers = {'Authorization': f'Bearer {self._key}'}
        body: Optional[bytes] = None
        url = f'{API_BASE}{path}'
        if data and method == 'GET':
            url += '?' + form_encode(data).decode('ascii')
        elif data is not None:
            body = form_encode(data)
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        if idempotency_key:
            headers['Idempotency-Key'] = idempotency_key
        status, payload = self._http(method, url, headers, body)
        if status >= 400:
            error = payload.get('error', {}) if isinstance(payload, dict) else {}
            if status == 401:
                raise GatewayError('The payment gateway is not configured correctly.', status=502)
            raise GatewayError(str(error.get('message') or 'The payment gateway rejected the request.'),
                               status=status)
        return payload

    def create_checkout_session(
        self, *, line_items: list[dict[str, Any]], method: str, success_url: str, cancel_url: str,
        customer_email: str, reference: str, expires_at: int,
    ) -> dict[str, Any]:
        """`line_items` entries: `name`, `unit_amount_sen` (positive int) and `quantity`."""
        stripe_type = STRIPE_METHOD_TYPES.get(method)
        if stripe_type is None:
            raise GatewayError(f'{method} cannot be paid through the gateway.', status=422)
        items = [{
            'quantity': item['quantity'],
            'price_data': {
                'currency': 'myr',
                'unit_amount': item['unit_amount_sen'],
                'product_data': {'name': str(item['name'])[:200] or 'Item'},
            },
        } for item in line_items]
        return self._call('POST', '/checkout/sessions', {
            'mode': 'payment',
            'payment_method_types': [stripe_type],
            'line_items': items,
            'success_url': success_url,
            'cancel_url': cancel_url,
            'customer_email': customer_email,
            'client_reference_id': reference,
            'metadata': {'session_id': reference},
            'expires_at': expires_at,
        }, idempotency_key=f'create-{reference}')

    def retrieve_session(self, gateway_session_id: str, expand: Optional[list[str]] = None) -> dict[str, Any]:
        return self._call('GET', f'/checkout/sessions/{urllib.parse.quote(gateway_session_id, safe="")}',
                          {'expand': expand} if expand else None)

    def expire_session(self, gateway_session_id: str) -> dict[str, Any]:
        return self._call('POST', f'/checkout/sessions/{urllib.parse.quote(gateway_session_id, safe="")}/expire', {})

    def refund(self, payment_intent_id: str, reference: str) -> dict[str, Any]:
        return self._call('POST', '/refunds', {'payment_intent': payment_intent_id},
                          idempotency_key=f'refund-{reference}')


def verify_webhook(payload: bytes, header: Optional[str], secret: str, *, now: Optional[float] = None,
                   tolerance: int = WEBHOOK_TOLERANCE_SECONDS) -> dict[str, Any]:
    """Check Stripe's `Stripe-Signature` header (`t=<unix>,v1=<hmac>`) and return the parsed event."""
    if not secret:
        raise WebhookSignatureError('webhook secret is not configured')
    if not header:
        raise WebhookSignatureError('missing signature header')
    timestamp: Optional[str] = None
    signatures: list[str] = []
    for part in header.split(','):
        key, _, value = part.strip().partition('=')
        if key == 't':
            timestamp = value
        elif key == 'v1':
            signatures.append(value)
    if not timestamp or not signatures or not timestamp.isdigit():
        raise WebhookSignatureError('malformed signature header')
    expected = hmac.new(secret.encode('utf-8'), f'{timestamp}.'.encode('utf-8') + payload,
                        hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in signatures):
        raise WebhookSignatureError('signature mismatch')
    if abs((time.time() if now is None else now) - int(timestamp)) > tolerance:
        raise WebhookSignatureError('timestamp outside tolerance')
    try:
        event = json.loads(payload.decode('utf-8'))
    except ValueError as exc:
        raise WebhookSignatureError('body is not JSON') from exc
    if not isinstance(event, dict):
        raise WebhookSignatureError('body is not an event')
    return event


def sign_webhook(payload: bytes, secret: str, timestamp: Optional[int] = None) -> str:
    """Header value for `payload`, the way Stripe builds it. Used by tests and local webhook checks."""
    ts = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode('utf-8'), f'{ts}.'.encode('utf-8') + payload, hashlib.sha256).hexdigest()
    return f't={ts},v1={digest}'
