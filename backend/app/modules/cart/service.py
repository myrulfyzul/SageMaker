"""Cart rules (Req 11): server-side pricing, quantity limits, stock checks, merge."""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ... import db
from ...errors import Conflict, NotFound, ValidationFailed
from ...time_utils import utc_now_iso
from ..inventory import api as inventory_api
from ..products import api as products_api
from . import repository as repo

MAX_LINE_QUANTITY = 20
DELIVERY_FEE_SEN = 800


class InsufficientStock(Conflict):
    code = 'insufficient_stock'
    message = 'Not enough stock for the requested quantity'


class ProductUnavailable(Conflict):
    code = 'product_unavailable'
    message = 'This product is not available'


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_quantity(value: Any, low: int = 1) -> int:
    if not _is_int(value) or not low <= value <= MAX_LINE_QUANTITY:
        raise ValidationFailed([{'field': 'quantity', 'reason': f'must be an integer from {low} to {MAX_LINE_QUANTITY}'}],
                               message=f'Quantity must be an integer from {low} to {MAX_LINE_QUANTITY}')
    return value


def _line_limit() -> ValidationFailed:
    return ValidationFailed([{'field': 'quantity', 'reason': f'a line can hold at most {MAX_LINE_QUANTITY}'}],
                            message=f'A single line can hold at most {MAX_LINE_QUANTITY} units', code='line_limit')


# ---- view --------------------------------------------------------------------------------------

def view(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    """Cart recomputed from current prices and stock; grand total = available line totals + delivery fee."""
    lines: list[dict[str, Any]] = []
    subtotal = 0
    for row in repo.list_lines(conn, user_id):
        pid, vid, qty = row['product_id'], row['variation_id'], int(row['quantity'])
        info = products_api.get_sellable(conn, pid, vid)
        stock = inventory_api.available_quantity(conn, pid, vid)
        available = info is not None and info['active'] and stock > 0
        unit = info['unitPriceSen'] if info else 0
        total = unit * qty
        if available:
            subtotal += total
        lines.append({
            'id': row['id'], 'productId': pid, 'variationId': vid,
            'name': info['name'] if info else None, 'variationLabel': info['variationLabel'] if info else None,
            'imageUrl': info['imageUrl'] if info else None, 'quantity': qty, 'unitPriceSen': unit,
            'lineTotalSen': total, 'available': available, 'availableQuantity': stock,
        })
    fee = DELIVERY_FEE_SEN if any(line['available'] for line in lines) else 0
    return {'lines': lines, 'subtotalSen': subtotal, 'deliveryFeeSen': fee, 'grandTotalSen': subtotal + fee}


# ---- changes -----------------------------------------------------------------------------------

def _require_sellable(conn: sqlite3.Connection, product_id: str, variation_id: Optional[int]) -> None:
    info = products_api.get_sellable(conn, product_id, variation_id)
    if info is None or not info['active']:
        raise ProductUnavailable()


def _check_stock(conn: sqlite3.Connection, product_id: str, variation_id: Optional[int], wanted: int) -> None:
    available = inventory_api.available_quantity(conn, product_id, variation_id)
    if wanted > available:
        raise InsufficientStock(f'Only {available} available', details=[
            {'productId': product_id, 'variationId': variation_id, 'requested': wanted, 'available': available}])


def add(conn: sqlite3.Connection, user_id: int, product_id: str, variation_id: Optional[int], quantity: Any) -> dict[str, Any]:
    qty = _check_quantity(quantity)
    with db.transaction(conn):
        _require_sellable(conn, product_id, variation_id)
        key = repo.sku_key(product_id, variation_id)
        existing = repo.find_line(conn, user_id, key)
        total = qty + (int(existing['quantity']) if existing else 0)
        if total > MAX_LINE_QUANTITY:
            raise _line_limit()
        _check_stock(conn, product_id, variation_id, total)
        repo.upsert_line(conn, user_id, product_id, variation_id, key, total, utc_now_iso())
    return view(conn, user_id)


def set_quantity(conn: sqlite3.Connection, user_id: int, product_id: str, variation_id: Optional[int],
                 quantity: Any) -> dict[str, Any]:
    qty = _check_quantity(quantity, low=0)
    key = repo.sku_key(product_id, variation_id)
    with db.transaction(conn):
        if qty == 0:
            repo.delete_by_key(conn, user_id, key)
        else:
            _require_sellable(conn, product_id, variation_id)
            _check_stock(conn, product_id, variation_id, qty)
            repo.upsert_line(conn, user_id, product_id, variation_id, key, qty, utc_now_iso())
    return view(conn, user_id)


def remove(conn: sqlite3.Connection, user_id: int, line_id: int) -> dict[str, Any]:
    with db.transaction(conn):
        if not repo.delete_by_id(conn, user_id, line_id):
            raise NotFound('Cart line not found')
    return view(conn, user_id)


def clear(conn: sqlite3.Connection, user_id: int) -> None:
    """Delete all lines inside the caller's transaction."""
    repo.delete_all(conn, user_id)


def merge(conn: sqlite3.Connection, user_id: int, guest_lines: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum guest quantities into the server cart, capped at 20 per line and at stock.
    Anything capped or rejected is reported in `notMerged` with the quantity left over."""
    not_merged: list[dict[str, Any]] = []

    def skip(pid: Any, vid: Any, qty: Any, reason: str) -> None:
        not_merged.append({'productId': pid, 'variationId': vid, 'quantity': qty, 'reason': reason})

    with db.transaction(conn):
        for item in guest_lines:
            pid, vid, qty = item.get('productId'), item.get('variationId'), item.get('quantity')
            if (not isinstance(pid, str) or not pid or not (vid is None or _is_int(vid))
                    or not _is_int(qty) or not 1 <= qty <= MAX_LINE_QUANTITY):
                skip(pid, vid, qty, 'invalid_line')
                continue
            info = products_api.get_sellable(conn, pid, vid)
            if info is None or not info['active']:
                skip(pid, vid, qty, 'unavailable')
                continue
            key = repo.sku_key(pid, vid)
            existing = repo.find_line(conn, user_id, key)
            current = int(existing['quantity']) if existing else 0
            stock = inventory_api.available_quantity(conn, pid, vid)
            target = min(current + qty, MAX_LINE_QUANTITY, max(stock, current))
            added = target - current
            if added > 0:
                repo.upsert_line(conn, user_id, pid, vid, key, target, utc_now_iso())
            if added < qty:
                skip(pid, vid, qty - added, 'line_limit' if stock >= MAX_LINE_QUANTITY else 'insufficient_stock')
    return {'cart': view(conn, user_id), 'notMerged': not_merged}
