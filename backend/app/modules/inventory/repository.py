"""SQL for the inventory-owned tables: stock_levels, stock_adjustments, inventory_settings.

Every function takes the caller's open connection and never starts or commits a transaction.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

DEFAULT_LOW_STOCK_THRESHOLD = 5


def sku_key(product_id: str, variation_id: Optional[int]) -> str:
    return product_id if variation_id is None else f'{product_id}#{variation_id}'


def insert_level(conn: sqlite3.Connection, key: str, product_id: str, variation_id: Optional[int], quantity: int) -> None:
    conn.execute(
        'INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) VALUES (?, ?, ?, ?, ?)',
        (key, product_id, variation_id, quantity, quantity))


def upsert_threshold(conn: sqlite3.Connection, product_id: str, threshold: int) -> None:
    conn.execute(
        'INSERT INTO inventory_settings (product_id, low_stock_threshold) VALUES (?, ?) '
        'ON CONFLICT(product_id) DO UPDATE SET low_stock_threshold = excluded.low_stock_threshold',
        (product_id, threshold))


def get_threshold(conn: sqlite3.Connection, product_id: str) -> int:
    row = conn.execute('SELECT low_stock_threshold FROM inventory_settings WHERE product_id = ?', (product_id,)).fetchone()
    return int(row['low_stock_threshold']) if row else DEFAULT_LOW_STOCK_THRESHOLD


def levels_for_product(conn: sqlite3.Connection, product_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        'SELECT sku_key, variation_id, quantity, opening_quantity FROM stock_levels WHERE product_id = ? '
        'ORDER BY (variation_id IS NOT NULL), variation_id', (product_id,)).fetchall()


def get_quantity(conn: sqlite3.Connection, key: str) -> Optional[int]:
    row = conn.execute('SELECT quantity FROM stock_levels WHERE sku_key = ?', (key,)).fetchone()
    return int(row['quantity']) if row else None


def decrement_if_available(conn: sqlite3.Connection, key: str, quantity: int) -> bool:
    """Conditional decrement: succeeds only when enough stock remains (second line of defence for Req 14.4)."""
    cur = conn.execute('UPDATE stock_levels SET quantity = quantity - ? WHERE sku_key = ? AND quantity >= ?',
                       (quantity, key, quantity))
    return cur.rowcount == 1


def increment(conn: sqlite3.Connection, key: str, quantity: int) -> bool:
    cur = conn.execute('UPDATE stock_levels SET quantity = quantity + ? WHERE sku_key = ?', (quantity, key))
    return cur.rowcount == 1


def insert_adjustment(conn: sqlite3.Connection, key: str, product_id: str, delta: int, reason: str,
                      actor_user_id: Optional[int], order_id: Optional[str], created_at: str) -> None:
    conn.execute(
        'INSERT INTO stock_adjustments (sku_key, product_id, delta, reason, actor_user_id, order_id, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)', (key, product_id, delta, reason, actor_user_id, order_id, created_at))


def net_reserved_for_order(conn: sqlite3.Connection, order_id: str) -> list[dict[str, Any]]:
    """Per SKU, the quantity still held by the order according to the ledger (reservations minus restorations)."""
    rows = conn.execute(
        'SELECT sku_key, product_id, -SUM(delta) AS held FROM stock_adjustments WHERE order_id = ? '
        'GROUP BY sku_key, product_id HAVING -SUM(delta) > 0 ORDER BY sku_key', (order_id,)).fetchall()
    return [{'sku_key': r['sku_key'], 'product_id': r['product_id'], 'held': int(r['held'])} for r in rows]


def product_totals(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Per product: summed quantity and effective threshold."""
    rows = conn.execute(
        'SELECT s.product_id AS product_id, SUM(s.quantity) AS quantity, '
        'COALESCE(i.low_stock_threshold, ?) AS threshold '
        'FROM stock_levels s LEFT JOIN inventory_settings i ON i.product_id = s.product_id '
        'GROUP BY s.product_id ORDER BY s.product_id', (DEFAULT_LOW_STOCK_THRESHOLD,)).fetchall()
    return [{'product_id': r['product_id'], 'quantity': int(r['quantity']), 'threshold': int(r['threshold'])} for r in rows]


def list_adjustments(conn: sqlite3.Connection, product_id: str) -> list[sqlite3.Row]:
    """Ledger rows of one product, newest first."""
    return conn.execute(
        'SELECT id, sku_key, delta, reason, actor_user_id, order_id, created_at FROM stock_adjustments '
        'WHERE product_id = ? ORDER BY id DESC', (product_id,)).fetchall()


def sku_rows(conn: sqlite3.Connection, product_id: str) -> dict[str, Optional[int]]:
    """`sku_key -> variation_id` for a product."""
    return {r['sku_key']: r['variation_id'] for r in levels_for_product(conn, product_id)}
