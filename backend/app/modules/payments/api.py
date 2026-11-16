"""The only surface other modules may import from `payments`.

`record` runs in the caller's transaction and never commits (Req 14.2). It does not check DEMO_MODE; HTTP callers
use `require_demo_mode` (Req 33.7)."""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import Request

from app.errors import AppError
from app.modules.payments.schemas import (PAYMENT_METHODS, PAYMENT_OUTCOMES, Method, PaymentRequest,  # noqa: F401 (re-exported)
                                         SimulatedOutcome, provider_problem)
from app.errors import ValidationFailed
from app.time_utils import utc_now_iso


class PaymentsNotConfigured(AppError):
    status = 503
    code = 'payments_not_configured'
    message = 'Real payments are not configured. This prototype only supports simulated payments.'


def require_demo_mode(request: Request) -> None:
    """503 unless DEMO_MODE is exactly `1`; raised before any write."""
    if not request.app.state.settings.demo_mode:
        raise PaymentsNotConfigured()


def _payment_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {'id': row['id'], 'orderId': row['order_id'], 'method': row['method'], 'outcome': row['outcome'],
            'amountSen': row['amount_sen'], 'provider': row['provider'] if 'provider' in row.keys() else None, 'isDemo': bool(row['is_demo']), 'createdAt': row['created_at']}


def validate_provider(method: str, provider: str | None) -> None:
    """422 naming `provider` when it does not belong to `method` (Malaysian banks and e-wallets only)."""
    reason = provider_problem(method, provider)
    if reason:
        raise ValidationFailed([{'field': 'provider', 'reason': reason}])


def record(conn: sqlite3.Connection, order_id: str, method: str, outcome: str, amount_sen: int,
           created_at: str | None = None, provider: str | None = None) -> dict[str, Any]:
    """Insert one Payment_Record (Req 13.4). `is_demo` is always 1. Earlier records are never modified."""
    if method not in PAYMENT_METHODS:
        raise ValueError(f'unsupported payment method: {method!r}')
    if outcome not in PAYMENT_OUTCOMES:
        raise ValueError(f'unsupported payment outcome: {outcome!r}')
    if (method == 'cod') != (outcome == 'pending_cod'):
        raise ValueError('cod payments are recorded as pending_cod and only cod uses pending_cod')
    if isinstance(amount_sen, bool) or not isinstance(amount_sen, int) or amount_sen <= 0:
        raise ValueError('amount_sen must be a positive integer')
    stamp = created_at or utc_now_iso()
    if provider is None:
        cur = conn.execute(
            'INSERT INTO payments (order_id, method, outcome, amount_sen, is_demo, created_at) VALUES (?,?,?,?,1,?)',
            (order_id, method, outcome, amount_sen, stamp))
    else:
        cur = conn.execute(
            'INSERT INTO payments (order_id, method, outcome, amount_sen, provider, is_demo, created_at) '
            'VALUES (?,?,?,?,?,1,?)', (order_id, method, outcome, amount_sen, provider, stamp))
    row = conn.execute('SELECT * FROM payments WHERE id = ?', (cur.lastrowid,)).fetchone()
    return _payment_dict(row)


def list_for_order(conn: sqlite3.Connection, order_id: str) -> list[dict[str, Any]]:
    rows = conn.execute('SELECT * FROM payments WHERE order_id = ? ORDER BY id', (order_id,)).fetchall()
    return [_payment_dict(r) for r in rows]
