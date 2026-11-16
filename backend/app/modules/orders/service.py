"""Orders use cases: customer views, payment retry and the staff status state machine (Req 13.11-13.12, 14.9-14.10,
15, 22). Writes run in one transaction; stock and notifications go through the other modules' `api`."""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from app import db
from app.errors import AppError, Conflict, NotFound, ValidationFailed
from app.modules.inventory import api as inventory_api
from app.modules.notifications import api as notifications_api
from app.modules.orders import api as orders_api
from app.modules.orders.schemas import StatusChange
from app.modules.payments import api as payments_api
from app.modules.production import api as production_api
from app.time_utils import utc_now_iso

STATUSES = ('placed', 'confirmed', 'preparing', 'shipped', 'delivered', 'cancelled', 'payment_failed')
_NEXT = {'placed': 'confirmed', 'confirmed': 'preparing', 'preparing': 'shipped', 'shipped': 'delivered'}
_CANCELLABLE = ('placed', 'confirmed', 'preparing')


class InvalidFilter(AppError):
    status = 422
    code = 'invalid_filter'
    message = 'Unknown status filter'


class InvalidTransition(Conflict):
    code = 'invalid_transition'


def customer_view(conn: sqlite3.Connection, order: dict[str, Any]) -> dict[str, Any]:
    """Order dict plus nested delivery, payments, timeline `status`/`at` aliases and `productionLabel` (Req 15.10)."""
    history = [{**h, 'status': h['newStatus'], 'at': h['createdAt']} for h in order['history']]
    delivery = {'name': order['customerName'], 'phone': order['phone'], 'email': order['email'],
                'address': order['deliveryAddress'], 'postcode': order['deliveryPostcode'],
                'state': order['deliveryState'], 'notes': order['deliveryNotes']}
    return {**order, 'history': history, 'delivery': delivery, 'productionLabel': production_api.production_label(conn, order['id']),
            'productionProgressPercent': production_api.production_progress(conn, order['id']),
            'payments': payments_api.list_for_order(conn, order['id'])}


def _summary(order: dict[str, Any]) -> dict[str, Any]:
    return {k: order[k] for k in ('id', 'status', 'paymentStatus', 'paymentMethod', 'customerName', 'totalSen',
                                  'shippingReference', 'isDemo', 'createdAt', 'updatedAt')} | {
        'itemCount': sum(ln['quantity'] for ln in order['lines']), 'lines': order['lines']}


def _page(items: list[dict[str, Any]], total: int, limit: int, offset: int) -> dict[str, Any]:
    return {'items': items, 'total': total, 'limit': limit, 'offset': offset,
            'hasMore': offset + len(items) < total}


def list_for_customer(conn: sqlite3.Connection, user_id: int, limit: int, offset: int) -> dict[str, Any]:
    orders, total = orders_api.list_orders(conn, user_id=user_id, limit=limit, offset=offset)
    return _page([_summary(o) for o in orders], total, limit, offset)


def customer_detail(conn: sqlite3.Connection, user_id: int, order_id: str) -> dict[str, Any]:
    if orders_api.order_owner_id(conn, order_id) != user_id:
        raise NotFound()  # foreign and missing are indistinguishable (Req 15.4)
    return customer_view(conn, orders_api.get_order(conn, order_id))


def list_for_staff(conn: sqlite3.Connection, status: Optional[str], q: Optional[str], limit: int,
                   offset: int) -> dict[str, Any]:
    if status is not None and status not in STATUSES:
        raise InvalidFilter(details=[{'field': 'status', 'reason': f'must be one of {", ".join(STATUSES)}'}])
    q = q.strip() if q else None
    orders, total = orders_api.list_orders(conn, statuses=(status,) if status else None, q=q or None,
                                           limit=limit, offset=offset)
    return _page([_summary(o) for o in orders], total, limit, offset)


def staff_detail(conn: sqlite3.Connection, order_id: str) -> dict[str, Any]:
    order = orders_api.get_order(conn, order_id)
    if order is None:
        raise NotFound()
    return customer_view(conn, order)


def _apply_change(conn: sqlite3.Connection, order: dict[str, Any], new_status: str, actor: Optional[int],
                  reason: Optional[str], **fields: Any) -> None:
    """Update the order and, because the status really changes, append one history row and one notification."""
    now = utc_now_iso()
    orders_api.update_fields(conn, order['id'], status=new_status, updated_at=now, **fields)
    orders_api.append_history(conn, order['id'], order['status'], new_status, actor, reason, now)
    notifications_api.order_status_changed(conn, order['id'], order['userId'], order['status'], new_status)


def change_status(conn: sqlite3.Connection, order_id: str, body: StatusChange, actor_user_id: int) -> dict[str, Any]:
    with db.transaction(conn):
        order = orders_api.get_order(conn, order_id)
        if order is None:
            raise NotFound()
        current, target = order['status'], body.status
        allowed = _NEXT.get(current) == target or (target == 'cancelled' and current in _CANCELLABLE)
        if not allowed:
            raise InvalidTransition(f'Cannot change order status from {current} to {target}',
                                    details=[{'current': current, 'requested': target}])
        fields: dict[str, Any] = {}
        reason: Optional[str] = None
        if target == 'shipped':
            ref = (body.shipping_reference or '').strip()
            if not 3 <= len(ref) <= 80:
                raise ValidationFailed([{'field': 'shipping_reference', 'reason': 'must be 3 to 80 characters'}])
            fields['shipping_reference'] = ref
        elif target == 'cancelled':
            reason = (body.reason or '').strip()
            if not 3 <= len(reason) <= 500:
                raise ValidationFailed([{'field': 'reason', 'reason': 'must be 3 to 500 characters'}])
            fields['cancel_reason'] = reason
        _apply_change(conn, order, target, actor_user_id, reason, **fields)
        if target == 'cancelled':
            inventory_api.restore_for_order(conn, order_id)  # once only (Req 14.10)
        elif target == 'confirmed':
            production_api.create_jobs_for_order(conn, order_id)  # same transaction; status untouched (Req 24.1)
        return staff_detail(conn, order_id)


_RETRY_OUTCOMES = {
    'success': ('paid', 'placed'),
    'cancelled': ('cancelled', 'cancelled'),
    'failed': ('failed', 'payment_failed'),
}


def retry_payment(conn: sqlite3.Connection, user_id: int, order_id: str, body: payments_api.PaymentRequest) -> dict[str, Any]:
    """Customer retry for an order in `payment_failed`: new Payment_Record each time, stock re-validated on success."""
    if body.method == 'cod':
        outcome, payment_status, target = 'pending_cod', 'pending_cod', 'placed'
    elif body.outcome is None:
        raise ValidationFailed([{'field': 'outcome', 'reason': 'required for card, fpx and ewallet'}])
    else:
        outcome = body.outcome
        payment_status, target = _RETRY_OUTCOMES[outcome]
    payments_api.validate_provider(body.method, body.provider)
    with db.transaction(conn):
        if orders_api.order_owner_id(conn, order_id) != user_id:
            raise NotFound()
        order = orders_api.get_order(conn, order_id)
        if order['status'] != 'payment_failed':
            raise InvalidTransition(f'Payment can only be retried for orders in payment_failed, not {order["status"]}',
                                    details=[{'current': order['status'], 'requested': 'payment_retry'}])
        if target == 'placed':
            # Raises InsufficientStock (409, per-item `available`) and rolls everything back, leaving the order as is.
            inventory_api.reserve_for_order(
                conn, [{'product_id': ln['productId'], 'variation_id': ln['variationId'], 'quantity': ln['quantity']}
                       for ln in order['lines']], order_id, user_id)
            orders_api.rearm_stock_restore(conn, order_id)
        payments_api.record(conn, order_id, body.method, outcome, order['totalSen'], provider=body.provider)
        orders_api.update_fields(conn, order_id, payment_status=payment_status, payment_provider=body.provider,
                                 updated_at=utc_now_iso())
        if target != 'payment_failed':
            _apply_change(conn, order, target, user_id, None)
        return customer_view(conn, orders_api.get_order(conn, order_id))
