"""Legacy prototype endpoints with unchanged request/response shapes.

Products and prices come from the products table (the bundled assets/products.json only fills an empty table).
Orders are guest orders (`user_id` NULL, `source='legacy'`) written through `orders.api` and the same stock
reservation path as app checkout. Only demo payments are implemented. No real cards, transactions, or couriers.
"""
from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ...db import connect, transaction
from ..inventory import api as inventory_api
from ..orders import api as orders_api
from ..products import api as products_api

REPO_ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = REPO_ROOT / 'assets' / 'products.json'
SHIPPING_FEE_SEN = 800  # RM8.00 DEMO flat delivery fee, NOT a Sagemaker quote
STATUS_FLOW = ('placed', 'packing', 'shipped', 'delivered')
BOOTSTRAP_STOCK = 100  # opening stock for products inserted from the bundled catalogue

router = APIRouter(prefix='/api/legacy', tags=['legacy'])


def bundled_catalog() -> list[dict]:
    return json.loads(CATALOG_PATH.read_text(encoding='utf-8'))


def _ensure_catalogue(conn) -> None:
    """Fill a completely empty products table from the bundled JSON (with stock) so a fresh database works."""
    if conn.execute('SELECT 1 FROM products LIMIT 1').fetchone() is not None:
        return
    with transaction(conn):
        for product_id in products_api.ensure_legacy_catalogue(conn, bundled_catalog()):
            inventory_api.initialise(conn, product_id, None, BOOTSTRAP_STOCK)


class BasketLine(BaseModel):
    product_id: str = Field(min_length=1, max_length=90)
    quantity: int = Field(ge=1, le=20)


class Checkout(BaseModel):
    checkout_id: str = Field(min_length=10, max_length=80)
    customer_name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=3, max_length=160)
    phone: str = Field(min_length=6, max_length=30)
    delivery_address: str = Field(min_length=10, max_length=300)
    payment_method: Literal['demo_card', 'demo_fpx', 'demo_ewallet']
    items: list[BasketLine] = Field(min_length=1, max_length=30)


class AdminStatus(BaseModel):
    status: Literal['placed', 'packing', 'shipped', 'delivered']
    tracking_number: str | None = Field(default=None, max_length=80)


def public_order(row: dict[str, Any]) -> dict:
    return {
        'id': row['id'], 'status': row['status'], 'paymentStatus': row['payment_status'],
        'paymentMethod': row['payment_method'], 'items': json.loads(row['items_json']),
        'shippingFeeSen': row['shipping_fee_sen'], 'totalSen': row['total_sen'],
        'trackingNumber': row['tracking_number'], 'createdAt': row['created_at'],
        'updatedAt': row['updated_at'],
    }


@router.get('/products')
def products(request: Request):
    conn = connect(request.app.state.settings.database_path)
    try:
        _ensure_catalogue(conn)
        return products_api.legacy_catalogue(conn)
    finally:
        conn.close()


@router.post('/orders', status_code=201)
def create_order(payload: Checkout, request: Request):
    settings = request.app.state.settings
    if not settings.demo_mode:
        raise HTTPException(503, 'Real payments are not configured. Ask the shop owner for a merchant gateway account.')
    if len({i.product_id for i in payload.items}) != len(payload.items):
        raise HTTPException(400, 'Duplicate product lines are not allowed')
    conn = connect(settings.database_path)
    try:
        _ensure_catalogue(conn)
        with transaction(conn):
            lines = []
            for line in payload.items:
                sellable = products_api.get_sellable(conn, line.product_id)
                if sellable is None or not sellable['active']:
                    raise HTTPException(400, f'Unknown product: {line.product_id}')
                lines.append({'product_id': line.product_id, 'name': sellable['name'],
                              'unit_price_sen': sellable['unitPriceSen'], 'quantity': line.quantity})
            if orders_api.checkout_id_exists(conn, payload.checkout_id):
                # checkout_id is an idempotency key, not authorization to read an order.
                raise HTTPException(409, 'Checkout already submitted. Check Orders in the app.')
            order, order_secret = orders_api.create_legacy_order(
                conn, checkout_id=payload.checkout_id, customer_name=payload.customer_name.strip(),
                email=payload.email.strip(), phone=payload.phone.strip(),
                delivery_address=payload.delivery_address.strip(), payment_method=payload.payment_method,
                shipping_fee_sen=SHIPPING_FEE_SEN, lines=lines)
            # Same reservation path as app checkout; a shortage raises 409 and rolls the order back.
            inventory_api.reserve_for_order(
                conn, [{'product_id': ln['product_id'], 'variation_id': None, 'quantity': ln['quantity']}
                       for ln in lines], order['id'], None)
        row = orders_api.get_legacy_record(conn, order['id'])
    finally:
        conn.close()
    return {**public_order(row), 'accessToken': order_secret}


@router.get('/orders/{order_id}')
def get_order(order_id: str, request: Request, x_order_token: str | None = Header(default=None)):
    if not x_order_token:
        raise HTTPException(401, 'Order token required')
    conn = connect(request.app.state.settings.database_path)
    try:
        row = orders_api.get_legacy_record(conn, order_id)
    finally:
        conn.close()
    if not row or not secrets.compare_digest(row['secret_token'].encode(), x_order_token.encode()):
        raise HTTPException(404, 'Order not found')
    return public_order(row)


@router.patch('/admin/orders/{order_id}/status')
def update_status(order_id: str, change: AdminStatus, request: Request,
                  x_admin_key: str | None = Header(default=None)):
    admin_key = request.app.state.settings.legacy_admin_key
    if not admin_key or not x_admin_key or not secrets.compare_digest(admin_key.encode(), x_admin_key.encode()):
        raise HTTPException(403, 'Admin key required')
    conn = connect(request.app.state.settings.database_path)
    try:
        with transaction(conn):
            row = orders_api.get_legacy_record(conn, order_id)
            if not row:
                raise HTTPException(404, 'Order not found')
            if row['status'] not in STATUS_FLOW:
                raise HTTPException(400, 'Order status cannot be changed through the legacy route')
            if STATUS_FLOW.index(change.status) < STATUS_FLOW.index(row['status']):
                raise HTTPException(400, 'Cannot move an order backwards')
            orders_api.set_legacy_status(conn, order_id, change.status, change.tracking_number)
        updated = orders_api.get_legacy_record(conn, order_id)
    finally:
        conn.close()
    return public_order(updated)
