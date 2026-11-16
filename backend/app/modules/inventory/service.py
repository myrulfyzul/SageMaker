"""Staff inventory use-cases (Req 21.1 to 21.7). Product names come from `products.api`, never from its tables."""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from app import db
from app.errors import NotFound
from app.modules.notifications import api as notifications_api
from app.modules.products import api as products_api

from . import api as inventory_api


def _with_names(conn: sqlite3.Connection, level: dict[str, Any]) -> dict[str, Any]:
    names = products_api.product_names(conn, [level['productId']])
    out = {**level, 'name': names.get(level['productId'], level['productId'])}
    if out.get('variations'):
        labels = products_api.variation_labels(conn, level['productId'])
        out['variations'] = [{**v, 'label': labels.get(v['variationId'])} for v in out['variations']]
    return out


def list_inventory(conn: sqlite3.Connection, low_only: bool) -> dict[str, Any]:
    levels = inventory_api.list_levels(conn)
    names = products_api.product_names(conn, [lv['productId'] for lv in levels])
    items = [{**lv, 'name': names.get(lv['productId'], lv['productId'])} for lv in levels]
    low_count = sum(1 for i in items if i['lowStock'])
    if low_only:
        items = [i for i in items if i['lowStock']]
    items.sort(key=lambda i: (i['name'].lower(), i['productId']))
    return {'items': items, 'lowStockCount': low_count}


def get_inventory(conn: sqlite3.Connection, product_id: str) -> dict[str, Any]:
    return _with_names(conn, inventory_api.get_level(conn, product_id))


def adjust(conn: sqlite3.Connection, product_id: str, variation_id: Optional[int], delta: int, reason: str,
           actor: int) -> dict[str, Any]:
    with db.transaction(conn):
        level = inventory_api.adjust(conn, product_id, variation_id, delta, reason, actor)
        if delta < 0 and level['lowStock']:
            names = products_api.product_names(conn, [product_id])
            notifications_api.low_stock(conn, product_id, names.get(product_id))
    return _with_names(conn, level)


def history(conn: sqlite3.Connection, product_id: str) -> list[dict[str, Any]]:
    if not inventory_api.repo.levels_for_product(conn, product_id):
        raise NotFound('No stock record for this product')
    return inventory_api.list_adjustments(conn, product_id)


def set_threshold(conn: sqlite3.Connection, product_id: str, threshold: int) -> dict[str, Any]:
    with db.transaction(conn):
        inventory_api.get_level(conn, product_id)  # 404 when unknown
        inventory_api.set_threshold(conn, product_id, threshold)
    return get_inventory(conn, product_id)
