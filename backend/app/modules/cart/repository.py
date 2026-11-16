"""SQL for the cart-owned table: cart_lines. Every function takes the caller's open connection."""
from __future__ import annotations

import sqlite3
from typing import Optional


def sku_key(product_id: str, variation_id: Optional[int]) -> str:
    return product_id if variation_id is None else f'{product_id}#{variation_id}'


def list_lines(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    return conn.execute('SELECT id, product_id, variation_id, quantity FROM cart_lines WHERE user_id = ? ORDER BY id',
                        (user_id,)).fetchall()


def find_line(conn: sqlite3.Connection, user_id: int, key: str) -> Optional[sqlite3.Row]:
    return conn.execute('SELECT id, quantity FROM cart_lines WHERE user_id = ? AND sku_key = ?', (user_id, key)).fetchone()


def upsert_line(conn: sqlite3.Connection, user_id: int, product_id: str, variation_id: Optional[int],
                key: str, quantity: int, now: str) -> None:
    conn.execute(
        'INSERT INTO cart_lines (user_id, product_id, variation_id, sku_key, quantity, created_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(user_id, sku_key) DO UPDATE SET quantity = excluded.quantity, '
        'updated_at = excluded.updated_at', (user_id, product_id, variation_id, key, quantity, now, now))


def delete_by_key(conn: sqlite3.Connection, user_id: int, key: str) -> None:
    conn.execute('DELETE FROM cart_lines WHERE user_id = ? AND sku_key = ?', (user_id, key))


def delete_by_id(conn: sqlite3.Connection, user_id: int, line_id: int) -> bool:
    return conn.execute('DELETE FROM cart_lines WHERE user_id = ? AND id = ?', (user_id, line_id)).rowcount == 1


def delete_all(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute('DELETE FROM cart_lines WHERE user_id = ?', (user_id,))
