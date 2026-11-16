"""The only surface other modules may import from `inventory`. All functions take the caller's open connection
and run inside the caller's transaction (checkout stays atomic, Req 14.2).

Staff adjust/threshold/history and the router belong to a later task (6.x); this file is the core used by
checkout, order cancellation and analytics.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Iterable, Mapping, Optional

from app.errors import AppError, Conflict, NotFound, ValidationFailed
from app.modules.orders import api as orders_api
from app.time_utils import utc_now_iso

from . import repository as repo

MAX_QUANTITY = 999_999_999
DEFAULT_LOW_STOCK_THRESHOLD = repo.DEFAULT_LOW_STOCK_THRESHOLD


class InsufficientStock(Conflict):
    """HTTP 409 listing each short product with its available quantity (Req 14.3)."""
    code = 'insufficient_stock'
    message = 'Insufficient stock'


def _check_int(value: Any, field: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValidationFailed([{'field': field, 'reason': f'must be an integer from {low} to {high}'}])
    return value


def initialise(conn: sqlite3.Connection, product_id: str, variation_id: Optional[int], quantity: int,
               threshold: int = repo.DEFAULT_LOW_STOCK_THRESHOLD) -> None:
    """Create the stock row (opening stock = quantity) and set the product's low-stock threshold."""
    _check_int(quantity, 'stock', 0, MAX_QUANTITY)
    _check_int(threshold, 'lowStockThreshold', 0, MAX_QUANTITY)
    key = repo.sku_key(product_id, variation_id)
    if repo.get_quantity(conn, key) is not None:
        raise Conflict('Stock already initialised for this product', code='stock_exists')
    repo.insert_level(conn, key, product_id, variation_id, quantity)
    repo.upsert_threshold(conn, product_id, threshold)


def get_level(conn: sqlite3.Connection, product_id: str) -> dict[str, Any]:
    """Stock, threshold and low-stock flag (quantity <= threshold). Product figure = sum over variations."""
    rows = repo.levels_for_product(conn, product_id)
    if not rows:
        raise NotFound('No stock record for this product')
    quantity = sum(int(r['quantity']) for r in rows)
    threshold = repo.get_threshold(conn, product_id)
    return {
        'productId': product_id,
        'quantity': quantity,
        'lowStockThreshold': threshold,
        'lowStock': quantity <= threshold,
        'variations': [{'variationId': r['variation_id'], 'quantity': int(r['quantity'])}
                       for r in rows if r['variation_id'] is not None],
    }


def reserve_for_order(conn: sqlite3.Connection, lines: Iterable[Mapping[str, Any]], order_id: str,
                      actor: Optional[int]) -> None:
    """Deduct stock for every line or for none.

    `lines`: mappings with `product_id`, `variation_id` (or None) and `quantity` >= 1. Each deduction is a conditional
    `UPDATE ... WHERE quantity >= ?`; the writes sit in a savepoint so a shortage leaves stock and ledger untouched.
    Raises InsufficientStock (409) listing every short line with `available`. One ledger row per SKU, delta < 0.
    """
    wanted: dict[str, dict[str, Any]] = {}
    for line in lines:
        qty = _check_int(line.get('quantity'), 'quantity', 1, MAX_QUANTITY)
        pid, vid = line['product_id'], line.get('variation_id')
        entry = wanted.setdefault(repo.sku_key(pid, vid), {'product_id': pid, 'variation_id': vid, 'quantity': 0})
        entry['quantity'] += qty

    now = utc_now_iso()
    short: list[dict[str, Any]] = []
    conn.execute('SAVEPOINT reserve_stock')
    try:
        for key, entry in wanted.items():
            if repo.decrement_if_available(conn, key, entry['quantity']):
                repo.insert_adjustment(conn, key, entry['product_id'], -entry['quantity'], 'Order placed',
                                       actor, order_id, now)
            else:
                short.append({'productId': entry['product_id'], 'variationId': entry['variation_id'],
                              'requested': entry['quantity'], 'available': repo.get_quantity(conn, key) or 0})
        if short:
            conn.execute('ROLLBACK TO SAVEPOINT reserve_stock')
    except BaseException:
        conn.execute('ROLLBACK TO SAVEPOINT reserve_stock')
        conn.execute('RELEASE SAVEPOINT reserve_stock')
        raise
    conn.execute('RELEASE SAVEPOINT reserve_stock')
    if short:
        raise InsufficientStock(details=short)


def restore_for_order(conn: sqlite3.Connection, order_id: str) -> bool:
    """Return the order's reserved stock, once only (Req 14.9, 14.10).

    Guarded by `orders.api.mark_stock_restored`; a repeat call changes nothing and returns False. Quantities come from
    this module's own ledger (rows for the order), one restoring ledger row per SKU.
    """
    if not orders_api.mark_stock_restored(conn, order_id):
        return False
    now = utc_now_iso()
    for held in repo.net_reserved_for_order(conn, order_id):
        if not repo.increment(conn, held['sku_key'], held['held']):
            raise AppError('Stock row missing during restore', code='stock_missing', status=500)
        repo.insert_adjustment(conn, held['sku_key'], held['product_id'], held['held'], 'Order restored',
                               None, order_id, now)
    return True


def low_stock_count(conn: sqlite3.Connection) -> int:
    """Number of products whose total stock is at or below their threshold."""
    return sum(1 for p in repo.product_totals(conn) if p['quantity'] <= p['threshold'])


def distribution_by_category(conn: sqlite3.Connection, category_by_product: Mapping[str, str]) -> list[dict[str, Any]]:
    """Total units in stock per category name, sorted by name.

    Inventory may not read `products`/`categories`, so the caller (analytics) passes `product_id -> category name`
    obtained from the products module. Products missing from the mapping are skipped.
    """
    totals: dict[str, int] = {}
    for p in repo.product_totals(conn):
        category = category_by_product.get(p['product_id'])
        if category is not None:
            totals[category] = totals.get(category, 0) + p['quantity']
    return [{'category': name, 'units': totals[name]} for name in sorted(totals)]


def set_threshold(conn: sqlite3.Connection, product_id: str, threshold: int) -> None:
    """Set the product's low-stock threshold (0 to 999,999,999)."""
    _check_int(threshold, 'lowStockThreshold', 0, MAX_QUANTITY)
    repo.upsert_threshold(conn, product_id, threshold)


def adjust(conn: sqlite3.Connection, product_id: str, variation_id: Optional[int], delta: Any, reason: Any,
           actor: Optional[int]) -> dict[str, Any]:
    """Staff stock adjustment (Req 21.2 to 21.4). Conditional update; a shortage changes nothing and stores nothing."""
    _check_int(delta, 'delta', -MAX_QUANTITY, MAX_QUANTITY)
    if delta == 0:
        raise ValidationFailed([{'field': 'delta', 'reason': 'must not be 0'}])
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 255:
        raise ValidationFailed([{'field': 'reason', 'reason': 'must be 1 to 255 characters'}])
    key = repo.sku_key(product_id, variation_id)
    current = repo.get_quantity(conn, key)
    if current is None:
        raise NotFound('No stock record for this product')
    ok = repo.decrement_if_available(conn, key, -delta) if delta < 0 else repo.increment(conn, key, delta)
    if not ok:
        raise InsufficientStock(details=[{'productId': product_id, 'variationId': variation_id,
                                          'requested': -delta, 'available': repo.get_quantity(conn, key) or 0}])
    repo.insert_adjustment(conn, key, product_id, delta, reason.strip(), actor, None, utc_now_iso())
    return get_level(conn, product_id)


def list_adjustments(conn: sqlite3.Connection, product_id: str) -> list[dict[str, Any]]:
    """Ledger of one product, newest first (Req 21.7); empty list when none."""
    variation_of = repo.sku_rows(conn, product_id)
    return [{'id': r['id'], 'productId': product_id, 'variationId': variation_of.get(r['sku_key']),
             'delta': int(r['delta']), 'reason': r['reason'], 'actorUserId': r['actor_user_id'],
             'orderId': r['order_id'], 'createdAt': r['created_at']}
            for r in repo.list_adjustments(conn, product_id)]


def list_levels(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every stocked product with quantity, threshold and low-stock flag, ordered by product id."""
    return [{'productId': p['product_id'], 'quantity': p['quantity'], 'lowStockThreshold': p['threshold'],
             'lowStock': p['quantity'] <= p['threshold']} for p in repo.product_totals(conn)]


def remove_for_product(conn: sqlite3.Connection, product_id: str) -> None:
    """Delete all stock rows, the threshold and the ledger for a product that is being permanently deleted."""
    conn.execute('DELETE FROM stock_adjustments WHERE product_id = ?', (product_id,))
    conn.execute('DELETE FROM stock_levels WHERE product_id = ?', (product_id,))
    conn.execute('DELETE FROM inventory_settings WHERE product_id = ?', (product_id,))


def available_quantity(conn: sqlite3.Connection, product_id: str, variation_id: Optional[int] = None) -> int:
    """Units in stock for one SKU (0 when there is no stock row)."""
    return repo.get_quantity(conn, repo.sku_key(product_id, variation_id)) or 0
