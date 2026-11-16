"""Checkout orchestration (Req 12, 13.3-13.7, 14): one transaction across cart, inventory, orders, payments and
notifications. This module owns no tables."""
from __future__ import annotations

import sqlite3
from typing import Any

from app import db
from app.errors import AppError, ValidationFailed
from app.modules.cart import api as cart_api
from app.modules.inventory import api as inventory_api
from app.modules.notifications import api as notifications_api
from app.modules.orders import api as orders_api
from app.modules.payments import api as payments_api

from .schemas import CheckoutIn, validate_delivery, validate_idempotency_key

# (method is cod?, outcome) -> (payment status, fulfilment status, payment-record outcome, restore stock)
_COD = ('pending_cod', 'placed', 'pending_cod', False)
_OUTCOMES = {
    'success': ('paid', 'placed', 'success', False),
    'failed': ('failed', 'payment_failed', 'failed', True),
    'cancelled': ('cancelled', 'cancelled', 'cancelled', True),
}


class EmptyCart(AppError):
    status = 400
    code = 'cart_empty'
    message = 'Your cart is empty'


def _outcome_mapping(body: CheckoutIn) -> tuple[str, str, str, bool]:
    if body.method == 'cod':
        return _COD
    if body.outcome is None:
        raise ValidationFailed([{'field': 'outcome', 'reason': 'required for card, fpx and ewallet'}])
    return _OUTCOMES[body.outcome]


def _with_payments(conn: sqlite3.Connection, order: dict[str, Any]) -> dict[str, Any]:
    return {**order, 'payments': payments_api.list_for_order(conn, order['id'])}


def place_order(conn: sqlite3.Connection, user_id: int, body: CheckoutIn) -> tuple[dict[str, Any], bool]:
    """Returns `(order, created)`; `created` is False for an idempotent repeat (HTTP 200, no writes)."""
    key = validate_idempotency_key(body.idempotency_key)
    delivery = validate_delivery(body.delivery)
    payment_status, fulfilment, record_outcome, restore = _outcome_mapping(body)

    with db.transaction(conn):
        existing = orders_api.find_by_idempotency_key(conn, user_id, key)
        if existing is not None:
            return _with_payments(conn, existing), False

        cart = cart_api.load_lines(conn, user_id)
        lines = cart['lines']
        if not lines:
            raise EmptyCart()
        unavailable = [{'productId': ln['productId'], 'variationId': ln['variationId'],
                        'requested': ln['quantity'], 'available': 0} for ln in lines if not ln['available']]
        if unavailable:
            raise inventory_api.InsufficientStock(details=unavailable)

        new_order = orders_api.NewOrder(
            user_id=user_id, idempotency_key=key, customer_name=delivery['name'], email=delivery['email'],
            phone=delivery['phone'], delivery_address=f"{delivery['address']}, {delivery['postcode']} {delivery['state']}",
            delivery_postcode=delivery['postcode'], delivery_state=delivery['state'],
            delivery_notes=delivery['notes'], payment_method=body.method, payment_status=payment_status,
            status=fulfilment, shipping_fee_sen=cart['deliveryFeeSen'],
            lines=[orders_api.NewOrderLine(product_id=ln['productId'], variation_id=ln['variationId'],
                                sku_key=(ln['productId'] if ln['variationId'] is None
                                         else f"{ln['productId']}#{ln['variationId']}"), name=ln['name'],
                                variation_label=ln['variationLabel'], unit_price_sen=ln['unitPriceSen'],
                                quantity=ln['quantity']) for ln in lines])
        order, _ = orders_api.create_order(conn, new_order, actor_user_id=user_id)
        order_id = order['id']

        inventory_api.reserve_for_order(
            conn, [{'product_id': ln['productId'], 'variation_id': ln['variationId'], 'quantity': ln['quantity']}
                   for ln in lines], order_id, user_id)
        payments_api.record(conn, order_id, body.method, record_outcome, order['totalSen'])
        if restore:
            inventory_api.restore_for_order(conn, order_id)
        cart_api.clear(conn, user_id)
        notifications_api.order_created(conn, order_id, user_id)
        return _with_payments(conn, orders_api.get_order(conn, order_id)), True
