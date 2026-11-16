"""The only surface other modules may import from `payments`.

`record` runs in the caller's transaction and never commits (Req 14.2). It does not check DEMO_MODE; HTTP callers
use `require_demo_mode` (Req 33.7).

Payment sessions (hosted-gateway attempts) live here too: they are payment data, and checkout drives them through
these functions without touching the table itself.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Optional

from fastapi import Request

from app.config import Settings
from app.errors import AppError, ValidationFailed
from app.modules.payments.gateway import (GATEWAY_EWALLET, STRIPE_METHOD_TYPES, GatewayError,  # noqa: F401 (re-exported)
                                          StripeGateway, WebhookSignatureError, sign_webhook, verify_webhook)
from app.modules.payments.schemas import (FPX_MAX_SEN, FPX_MIN_SEN, PAYMENT_METHODS, PAYMENT_OUTCOMES,  # noqa: F401 (re-exported)
                                         Method, PaymentRequest, SimulatedOutcome, provider_problem)
from app.time_utils import utc_now_iso


class PaymentsNotConfigured(AppError):
    status = 503
    code = 'payments_not_configured'
    message = 'Payments are not configured on this server.'


class UseGateway(AppError):
    status = 409
    code = 'use_payment_gateway'
    message = 'Online payments are completed on the secure payment page. Start the payment from checkout.'


class GatewayUnavailable(AppError):
    status = 502
    code = 'payment_gateway_error'
    message = 'The payment gateway could not complete the request.'


def require_demo_mode(request: Request) -> None:
    """503 unless DEMO_MODE is exactly `1` or a payment gateway is configured; raised before any write."""
    settings = request.app.state.settings
    if not (settings.demo_mode or settings.gateway_enabled):
        raise PaymentsNotConfigured()


def reject_simulated_when_gateway(settings: Settings, method: str) -> None:
    """With a real gateway configured, only cash on delivery may skip it. Otherwise a client could mark an
    order paid by sending `outcome: success` without paying."""
    if settings.gateway_enabled and method != 'cod':
        raise UseGateway()


def gateway_methods(settings: Settings) -> list[str]:
    """Methods the checkout may offer: the gateway's own, plus cash on delivery."""
    if settings.gateway_enabled:
        return [*STRIPE_METHOD_TYPES, 'cod']
    return [*PAYMENT_METHODS]


def _payment_dict(row: sqlite3.Row) -> dict[str, Any]:
    keys = row.keys()
    return {'id': row['id'], 'orderId': row['order_id'], 'method': row['method'], 'outcome': row['outcome'],
            'amountSen': row['amount_sen'], 'provider': row['provider'] if 'provider' in keys else None,
            'reference': row['reference'] if 'reference' in keys else None,
            'isDemo': bool(row['is_demo']), 'createdAt': row['created_at']}


def validate_provider(method: str, provider: str | None) -> None:
    """422 naming `provider` when it does not belong to `method` (Malaysian banks and e-wallets only)."""
    reason = provider_problem(method, provider)
    if reason:
        raise ValidationFailed([{'field': 'provider', 'reason': reason}])


def record(conn: sqlite3.Connection, order_id: str, method: str, outcome: str, amount_sen: int,
           created_at: str | None = None, provider: str | None = None,
           reference: str | None = None) -> dict[str, Any]:
    """Insert one Payment_Record (Req 13.4). `is_demo` is always 1 (sandbox money). Earlier records are never
    modified. `reference` is the gateway's id for the charge, when there is one."""
    if method not in PAYMENT_METHODS:
        raise ValueError(f'unsupported payment method: {method!r}')
    if outcome not in PAYMENT_OUTCOMES:
        raise ValueError(f'unsupported payment outcome: {outcome!r}')
    if (method == 'cod') != (outcome == 'pending_cod'):
        raise ValueError('cod payments are recorded as pending_cod and only cod uses pending_cod')
    if isinstance(amount_sen, bool) or not isinstance(amount_sen, int) or amount_sen <= 0:
        raise ValueError('amount_sen must be a positive integer')
    columns = ['order_id', 'method', 'outcome', 'amount_sen', 'is_demo', 'created_at']
    values: list[Any] = [order_id, method, outcome, amount_sen, 1, created_at or utc_now_iso()]
    for name, value in (('provider', provider), ('reference', reference)):
        if value is not None:
            columns.append(name)
            values.append(value)
    cur = conn.execute(
        f'INSERT INTO payments ({", ".join(columns)}) VALUES ({", ".join("?" * len(columns))})', values)
    row = conn.execute('SELECT * FROM payments WHERE id = ?', (cur.lastrowid,)).fetchone()
    return _payment_dict(row)


def list_for_order(conn: sqlite3.Connection, order_id: str) -> list[dict[str, Any]]:
    rows = conn.execute('SELECT * FROM payments WHERE order_id = ? ORDER BY id', (order_id,)).fetchall()
    return [_payment_dict(r) for r in rows]


# --- hosted-gateway payment sessions ------------------------------------------------------------------------

SESSION_STATUSES = ('pending', 'paid', 'cancelled', 'expired', 'failed', 'refunded')


def new_session_id() -> str:
    return f'PS-{uuid.uuid4().hex[:16].upper()}'


def _session_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {'id': row['id'], 'userId': row['user_id'], 'idempotencyKey': row['idempotency_key'],
            'gateway': row['gateway'], 'gatewaySessionId': row['gateway_session_id'],
            'checkoutUrl': row['checkout_url'], 'method': row['method'], 'provider': row['provider'],
            'amountSen': row['amount_sen'], 'delivery': json.loads(row['delivery_json']), 'status': row['status'],
            'orderId': row['order_id'], 'failureReason': row['failure_reason'],
            'createdAt': row['created_at'], 'updatedAt': row['updated_at']}


def create_session(conn: sqlite3.Connection, *, session_id: str, user_id: int, idempotency_key: str, gateway: str,
                   gateway_session_id: str, checkout_url: str, method: str, provider: Optional[str],
                   amount_sen: int, delivery: dict[str, Any]) -> dict[str, Any]:
    """Insert a pending session. Caller's transaction."""
    now = utc_now_iso()
    conn.execute(
        'INSERT INTO payment_sessions (id, user_id, idempotency_key, gateway, gateway_session_id, checkout_url, '
        'method, provider, amount_sen, delivery_json, status, created_at, updated_at) '
        "VALUES (?,?,?,?,?,?,?,?,?,?,'pending',?,?)",
        (session_id, user_id, idempotency_key, gateway, gateway_session_id, checkout_url, method, provider,
         amount_sen, json.dumps(delivery, sort_keys=True), now, now))
    return get_session(conn, session_id)  # type: ignore[return-value]


def get_session(conn: sqlite3.Connection, session_id: str) -> Optional[dict[str, Any]]:
    row = conn.execute('SELECT * FROM payment_sessions WHERE id = ?', (session_id,)).fetchone()
    return _session_dict(row) if row else None


def find_session_by_key(conn: sqlite3.Connection, user_id: int, key: str) -> Optional[dict[str, Any]]:
    row = conn.execute('SELECT * FROM payment_sessions WHERE user_id = ? AND idempotency_key = ?',
                       (user_id, key)).fetchone()
    return _session_dict(row) if row else None


def find_session_by_gateway_id(conn: sqlite3.Connection, gateway_session_id: str) -> Optional[dict[str, Any]]:
    row = conn.execute('SELECT * FROM payment_sessions WHERE gateway_session_id = ?',
                       (gateway_session_id,)).fetchone()
    return _session_dict(row) if row else None


def finish_session(conn: sqlite3.Connection, session_id: str, status: str, *, order_id: Optional[str] = None,
                   reason: Optional[str] = None) -> bool:
    """Move a `pending` session to a final status. Returns False when it was already final (no change). The
    caller's transaction; a final session is never changed again."""
    if status not in SESSION_STATUSES or status == 'pending':
        raise ValueError(f'not a final session status: {status!r}')
    cur = conn.execute(
        "UPDATE payment_sessions SET status = ?, order_id = COALESCE(?, order_id), failure_reason = ?, "
        "updated_at = ? WHERE id = ? AND status = 'pending'",
        (status, order_id, reason, utc_now_iso(), session_id))
    return cur.rowcount == 1
