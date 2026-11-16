"""The only surface other modules may import from `orders`.

Every function takes the caller's open connection; none starts or commits a transaction, so checkout stays atomic
(Req 14.2). SQL lives in `orders/repository.py`.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import string
from datetime import timedelta
from typing import Any, Callable, Optional

from app.config import DEFAULT_TIMEZONE
from app.errors import Conflict
from app.modules.orders import repository as repo
from app.modules.orders.schemas import NewOrder, NewOrderLine, normalise_status  # noqa: F401 (NewOrderLine re-exported)
from app.time_utils import month_bucket, utc_now, utc_now_iso

ORDER_ID_PREFIX = 'SM-'
ORDER_ID_ALPHABET = string.ascii_uppercase + string.digits
ORDER_ID_LENGTH = 10
MAX_ID_ATTEMPTS = 5


def new_order_id() -> str:
    return ORDER_ID_PREFIX + ''.join(secrets.choice(ORDER_ID_ALPHABET) for _ in range(ORDER_ID_LENGTH))


def scoped_checkout_id(user_id: int, key: str) -> str:
    """The stored `checkout_id` is `"{user_id}:{key}"` (design: idempotency scoped to the user)."""
    return f'{user_id}:{key}'


def _line_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {'id': row['id'], 'productId': row['product_id'], 'variationId': row['variation_id'],
            'skuKey': row['sku_key'], 'name': row['name'], 'variationLabel': row['variation_label'],
            'unitPriceSen': row['unit_price_sen'], 'quantity': row['quantity'], 'lineTotalSen': row['line_total_sen']}


def history(conn: sqlite3.Connection, order_id: str) -> list[dict[str, Any]]:
    """Timeline for an order, oldest first. Orders with no history rows (legacy) get a synthetic first entry built
    from `created_at`; it is returned only, never written (design: orders)."""
    rows = repo.history_for_order(conn, order_id)
    if rows:
        return [{'previousStatus': normalise_status(r['previous_status']) if r['previous_status'] else None,
                 'newStatus': normalise_status(r['new_status']), 'actorUserId': r['actor_user_id'],
                 'reason': r['reason'], 'createdAt': r['created_at'], 'synthetic': False} for r in rows]
    order = repo.get_order_row(conn, order_id)
    if order is None:
        return []
    return [{'previousStatus': None, 'newStatus': 'placed', 'actorUserId': None, 'reason': None,
             'createdAt': order['created_at'], 'synthetic': True}]


def _order_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    keys = row.keys()
    return {
        'id': row['id'], 'userId': row['user_id'], 'source': row['source'], 'isDemo': bool(row['is_demo']),
        'status': normalise_status(row['status']), 'paymentStatus': row['payment_status'],
        'paymentMethod': row['payment_method'],
        'paymentProvider': row['payment_provider'] if 'payment_provider' in keys else None,
        'customerName': row['customer_name'], 'email': row['email'],
        'phone': row['phone'], 'deliveryAddress': row['delivery_address'],
        'deliveryPostcode': row['delivery_postcode'], 'deliveryState': row['delivery_state'],
        'deliveryNotes': row['delivery_notes'], 'subtotalSen': row['subtotal_sen'],
        'shippingFeeSen': row['shipping_fee_sen'], 'totalSen': row['total_sen'],
        'shippingReference': row['shipping_reference'] if row['shipping_reference'] else row['tracking_number'],
        'cancelReason': row['cancel_reason'], 'stockRestored': bool(row['stock_restored']),
        'createdAt': row['created_at'], 'updatedAt': row['updated_at'],
        'checkoutId': row['checkout_id'] if 'checkout_id' in keys else None,
        'lines': [_line_dict(r) for r in repo.lines_for_order(conn, row['id'])],
        'history': history(conn, row['id']),
    }


def get_order(conn: sqlite3.Connection, order_id: str) -> Optional[dict[str, Any]]:
    row = repo.get_order_row(conn, order_id)
    return _order_dict(conn, row) if row else None


def find_by_idempotency_key(conn: sqlite3.Connection, user_id: int, key: str) -> Optional[dict[str, Any]]:
    row = repo.get_by_checkout_id(conn, scoped_checkout_id(user_id, key))
    return _order_dict(conn, row) if row else None


def append_history(conn: sqlite3.Connection, order_id: str, previous_status: Optional[str], new_status: str,
                   actor_user_id: Optional[int] = None, reason: Optional[str] = None,
                   created_at: Optional[str] = None) -> None:
    """Append one `order_history` row (the table is append-only by trigger)."""
    repo.insert_history(conn, order_id, previous_status, new_status, actor_user_id, reason, created_at or utc_now_iso())


def create_order(conn: sqlite3.Connection, order: NewOrder, *, actor_user_id: Optional[int] = None,
                 id_factory: Callable[[], str] = new_order_id) -> tuple[dict[str, Any], bool]:
    """Insert an order with its lines, `items_json` snapshot and first history row.

    Returns `(order, created)`. When the scoped checkout id already exists the original order is returned with
    `created=False` and nothing is written (idempotent repeat). An id collision retries with a new id, up to 5 times.
    Runs in the caller's transaction.
    """
    checkout_id = scoped_checkout_id(order.user_id, order.idempotency_key)
    existing = repo.get_by_checkout_id(conn, checkout_id)
    if existing is not None:
        return _order_dict(conn, existing), False

    lines = []
    for ln in order.lines:
        data = ln.model_dump()
        data['line_total_sen'] = ln.unit_price_sen * ln.quantity
        lines.append(data)
    subtotal = sum(ln['line_total_sen'] for ln in lines)
    items_json = json.dumps([{'productId': ln['product_id'], 'variationId': ln['variation_id'], 'name': ln['name'],
                              'variationLabel': ln['variation_label'], 'quantity': ln['quantity'],
                              'unitPriceSen': ln['unit_price_sen'], 'lineTotalSen': ln['line_total_sen']}
                             for ln in lines])
    now = order.created_at or utc_now_iso()
    base = {
        'checkout_id': checkout_id, 'secret_token': secrets.token_urlsafe(32), 'customer_name': order.customer_name,
        'email': order.email, 'phone': order.phone, 'delivery_address': order.delivery_address,
        'payment_method': order.payment_method, 'payment_status': order.payment_status, 'status': order.status,
        'shipping_fee_sen': order.shipping_fee_sen, 'total_sen': subtotal + order.shipping_fee_sen,
        'items_json': items_json, 'created_at': now, 'updated_at': now, 'user_id': order.user_id,
        'source': order.source, 'is_demo': order.is_demo, 'delivery_postcode': order.delivery_postcode,
        'delivery_state': order.delivery_state, 'delivery_notes': order.delivery_notes, 'subtotal_sen': subtotal,
    }
    order_id = None
    for _ in range(MAX_ID_ATTEMPTS):
        candidate = id_factory()
        # A savepoint keeps a unique violation from poisoning the caller's transaction.
        conn.execute('SAVEPOINT order_insert')
        try:
            repo.insert_order(conn, {'id': candidate, **base})
        except sqlite3.IntegrityError:
            conn.execute('ROLLBACK TO order_insert')
            conn.execute('RELEASE order_insert')
            if repo.get_order_row(conn, candidate) is None:
                raise  # not an id collision (e.g. a concurrent duplicate checkout id)
            continue
        conn.execute('RELEASE order_insert')
        order_id = candidate
        break
    if order_id is None:
        raise Conflict('Could not allocate an order id. Please try again.', code='order_id_unavailable')

    for ln in lines:
        repo.insert_line(conn, order_id, ln)
    append_history(conn, order_id, None, order.status, actor_user_id, None, now)
    return get_order(conn, order_id), True  # type: ignore[return-value]


def mark_stock_restored(conn: sqlite3.Connection, order_id: str) -> bool:
    """Atomically flag the order as stock-restored.

    Returns True only for the call that flips `stock_restored` from 0 to 1 (the caller must then restore stock);
    False when the order is unknown or was already restored. Runs in the caller's transaction.
    """
    return repo.set_stock_restored(conn, order_id, utc_now_iso())


def product_in_any_order(conn: sqlite3.Connection, product_id: str) -> bool:
    """True when any order line references the product (Req 20.8, 20.9)."""
    return repo.product_in_any_order(conn, product_id)


def units_sold_since(conn: sqlite3.Connection, days: int = 90) -> dict[str, int]:
    """Units sold per product over the last `days` days, from revenue-eligible orders."""
    cutoff = (utc_now() - timedelta(days=days)).isoformat()
    return {r['product_id']: int(r['units']) for r in repo.units_sold_since(conn, cutoff)}


def purchased_product_ids(conn: sqlite3.Connection, user_id: int) -> set[str]:
    """Product ids the user has ordered (cancelled and payment-failed orders excluded)."""
    return set(repo.purchased_product_ids(conn, user_id))


def sales_rows(conn: sqlite3.Connection, start: str, end: str) -> list[dict[str, Any]]:
    """Revenue-eligible orders with their lines for `start <= created_at < end` (ISO timestamps)."""
    by_order: dict[str, list[dict[str, Any]]] = {}
    for r in repo.sales_lines(conn, start, end):
        by_order.setdefault(r['order_id'], []).append(
            {'productId': r['product_id'], 'variationId': r['variation_id'], 'name': r['name'],
             'unitPriceSen': r['unit_price_sen'], 'quantity': r['quantity'], 'lineTotalSen': r['line_total_sen']})
    return [{'id': r['id'], 'createdAt': r['created_at'], 'status': normalise_status(r['status']),
             'paymentStatus': r['payment_status'], 'source': r['source'], 'subtotalSen': r['subtotal_sen'],
             'shippingFeeSen': r['shipping_fee_sen'], 'totalSen': r['total_sen'], 'lines': by_order.get(r['id'], [])}
            for r in repo.sales_orders(conn, start, end)]


def order_owner_id(conn: sqlite3.Connection, order_id: str) -> Optional[int]:
    """`user_id` of the order, or None when the order does not exist (or has no owner).

    Callers answering a customer must map "missing" and "foreign" to the same 404."""
    row = repo.get_order_row(conn, order_id)
    return row['user_id'] if row is not None else None


def order_exists(conn: sqlite3.Connection, order_id: str) -> bool:
    return repo.get_order_row(conn, order_id) is not None


def monthly_units(conn: sqlite3.Connection, product_id: str,
                  tz_name: str = DEFAULT_TIMEZONE) -> list[tuple[str, int, bool]]:
    """`(month 'YYYY-MM', units, has_synthetic)` per month with sales, ascending, bucketed in `tz_name`."""
    months: dict[str, list] = {}
    for r in repo.product_sale_lines(conn, product_id):
        bucket = months.setdefault(month_bucket(r['created_at'], tz_name), [0, False])
        bucket[0] += int(r['quantity'])
        bucket[1] = bucket[1] or r['source'] == 'synthetic'
    return [(m, v[0], v[1]) for m, v in sorted(months.items())]


def list_orders(conn: sqlite3.Connection, *, user_id: Optional[int] = None, statuses: Optional[tuple[str, ...]] = None,
                q: Optional[str] = None, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    """Full order dicts (newest first) and the total match count. A `preparing` filter also matches legacy `packing`."""
    stored = None
    if statuses:
        stored = tuple(dict.fromkeys(s for st in statuses for s in
                                     ((st, 'packing') if st == 'preparing' else (st,))))
    rows, total = repo.list_orders(conn, user_id=user_id, statuses=stored, q=q, limit=limit, offset=offset)
    return [_order_dict(conn, r) for r in rows], total


def update_fields(conn: sqlite3.Connection, order_id: str, **fields: Any) -> None:
    """Update status / payment_status / shipping_reference / cancel_reason / updated_at. Caller's transaction."""
    repo.update_order_fields(conn, order_id, **fields)


def rearm_stock_restore(conn: sqlite3.Connection, order_id: str) -> None:
    """Call after stock is reserved again for an order whose stock was restored (payment retry)."""
    repo.clear_stock_restored(conn, order_id)


def stored_status(conn: sqlite3.Connection, order_id: str) -> Optional[str]:
    row = repo.get_order_row(conn, order_id)
    return normalise_status(row['status']) if row is not None else None


# --- Legacy guest orders (/api/legacy, Req 1.1, 1.2, 22.13) -------------------------------------------------------

LEGACY_ID_PREFIX = 'DEMO-'
LEGACY_PAYMENT_STATUS = 'demo_simulated_not_charged'


def checkout_id_exists(conn: sqlite3.Connection, checkout_id: str) -> bool:
    """True when an order already uses this raw (unscoped) checkout id."""
    return repo.get_by_checkout_id(conn, checkout_id) is not None


def create_legacy_order(conn: sqlite3.Connection, *, checkout_id: str, customer_name: str, email: str, phone: str,
                        delivery_address: str, payment_method: str, shipping_fee_sen: int,
                        lines: list[dict[str, Any]],
                        id_factory: Optional[Callable[[], str]] = None) -> tuple[dict[str, Any], str]:
    """Insert a guest order (`user_id` NULL, `source='legacy'`, `DEMO-` id, status `placed`).

    `lines`: dicts with `product_id`, `name`, `unit_price_sen`, `quantity`. Writes `order_lines`, the `items_json`
    snapshot in the legacy shape and the first history row. Returns `(order, access_token)`. Runs in the caller's
    transaction; the caller reserves stock afterwards and checks `checkout_id_exists` first.
    """
    factory = id_factory or (lambda: LEGACY_ID_PREFIX + secrets.token_hex(5).upper())
    rows = []
    for ln in lines:
        rows.append({'product_id': ln['product_id'], 'variation_id': None, 'sku_key': ln['product_id'],
                     'name': ln['name'], 'variation_label': None, 'unit_price_sen': ln['unit_price_sen'],
                     'quantity': ln['quantity'], 'line_total_sen': ln['unit_price_sen'] * ln['quantity']})
    subtotal = sum(r['line_total_sen'] for r in rows)
    items_json = json.dumps([{'productId': r['product_id'], 'name': r['name'], 'quantity': r['quantity'],
                              'unitPriceSen': r['unit_price_sen'], 'lineTotalSen': r['line_total_sen']}
                             for r in rows])
    now = utc_now_iso()
    token = secrets.token_urlsafe(32)
    base = {
        'checkout_id': checkout_id, 'secret_token': token, 'customer_name': customer_name, 'email': email,
        'phone': phone, 'delivery_address': delivery_address, 'payment_method': payment_method,
        'payment_status': LEGACY_PAYMENT_STATUS, 'status': 'placed', 'shipping_fee_sen': shipping_fee_sen,
        'total_sen': subtotal + shipping_fee_sen, 'items_json': items_json, 'tracking_number': None,
        'created_at': now, 'updated_at': now, 'user_id': None, 'source': 'legacy', 'is_demo': 1,
        'subtotal_sen': subtotal,
    }
    order_id = None
    for _ in range(MAX_ID_ATTEMPTS):
        candidate = factory()
        conn.execute('SAVEPOINT legacy_order_insert')
        try:
            repo.insert_order(conn, {'id': candidate, **base})
        except sqlite3.IntegrityError:
            conn.execute('ROLLBACK TO legacy_order_insert')
            conn.execute('RELEASE legacy_order_insert')
            if repo.get_order_row(conn, candidate) is None:
                raise
            continue
        conn.execute('RELEASE legacy_order_insert')
        order_id = candidate
        break
    if order_id is None:
        raise Conflict('Could not allocate an order id. Please try again.', code='order_id_unavailable')
    for r in rows:
        repo.insert_line(conn, order_id, r)
    append_history(conn, order_id, None, 'placed', None, None, now)
    return get_order(conn, order_id), token  # type: ignore[return-value]


def get_legacy_record(conn: sqlite3.Connection, order_id: str) -> Optional[dict[str, Any]]:
    """Raw legacy-shaped record (status stored as-is, `items_json`, `secret_token`) for the legacy routes only."""
    row = repo.get_order_row(conn, order_id)
    if row is None:
        return None
    return {k: row[k] for k in ('id', 'status', 'payment_status', 'payment_method', 'items_json', 'shipping_fee_sen',
                                'total_sen', 'tracking_number', 'created_at', 'updated_at', 'secret_token')}


def set_legacy_status(conn: sqlite3.Connection, order_id: str, status: str,
                      tracking_number: Optional[str]) -> None:
    """Move an order along the legacy flow, keeping the stored tracking number when none is given, and append one
    history row when the status really changes."""
    row = repo.get_order_row(conn, order_id)
    if row is None:
        return
    now = utc_now_iso()
    tracking = tracking_number or row['tracking_number']
    conn.execute('UPDATE orders SET status=?, tracking_number=?, shipping_reference=?, updated_at=? WHERE id=?',
                 (status, tracking, tracking, now, order_id))
    if row['status'] != status:
        append_history(conn, order_id, row['status'], status, None, None, now)
