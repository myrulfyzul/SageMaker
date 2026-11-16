"""SQL for the orders-owned tables: orders, order_lines, order_history.

Every function takes the caller's open connection and never starts or commits a transaction.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from app.modules.orders.schemas import NON_REVENUE_STATUSES, REVENUE_PAYMENT_STATUSES

_ELIGIBLE = (
    "o.status NOT IN ({s}) AND o.payment_status IN ({p})".format(
        s=','.join("'%s'" % v for v in NON_REVENUE_STATUSES),
        p=','.join("'%s'" % v for v in REVENUE_PAYMENT_STATUSES)))


def insert_order(conn: sqlite3.Connection, values: dict[str, Any]) -> None:
    cols = list(values)
    conn.execute(f'INSERT INTO orders ({", ".join(cols)}) VALUES ({", ".join("?" for _ in cols)})',
                 [values[c] for c in cols])


def insert_line(conn: sqlite3.Connection, order_id: str, line: dict[str, Any]) -> None:
    conn.execute(
        'INSERT INTO order_lines (order_id, product_id, variation_id, sku_key, name, variation_label, unit_price_sen, '
        'quantity, line_total_sen) VALUES (?,?,?,?,?,?,?,?,?)',
        (order_id, line['product_id'], line['variation_id'], line['sku_key'], line['name'], line['variation_label'],
         line['unit_price_sen'], line['quantity'], line['line_total_sen']))


def insert_history(conn: sqlite3.Connection, order_id: str, previous_status: Optional[str], new_status: str,
                   actor_user_id: Optional[int], reason: Optional[str], created_at: str) -> None:
    conn.execute(
        'INSERT INTO order_history (order_id, previous_status, new_status, actor_user_id, reason, created_at) '
        'VALUES (?,?,?,?,?,?)', (order_id, previous_status, new_status, actor_user_id, reason, created_at))


def get_order_row(conn: sqlite3.Connection, order_id: str) -> Optional[sqlite3.Row]:
    return conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()


def get_by_checkout_id(conn: sqlite3.Connection, checkout_id: str) -> Optional[sqlite3.Row]:
    return conn.execute('SELECT * FROM orders WHERE checkout_id = ?', (checkout_id,)).fetchone()


def lines_for_order(conn: sqlite3.Connection, order_id: str) -> list[sqlite3.Row]:
    return conn.execute('SELECT * FROM order_lines WHERE order_id = ? ORDER BY id', (order_id,)).fetchall()


def history_for_order(conn: sqlite3.Connection, order_id: str) -> list[sqlite3.Row]:
    return conn.execute('SELECT * FROM order_history WHERE order_id = ? ORDER BY id', (order_id,)).fetchall()


def set_stock_restored(conn: sqlite3.Connection, order_id: str, when: str) -> bool:
    cur = conn.execute('UPDATE orders SET stock_restored = 1, stock_restored_at = ? WHERE id = ? AND stock_restored = 0',
                       (when, order_id))
    return cur.rowcount == 1


def product_in_any_order(conn: sqlite3.Connection, product_id: str) -> bool:
    return conn.execute('SELECT 1 FROM order_lines WHERE product_id = ? LIMIT 1', (product_id,)).fetchone() is not None


def units_sold_since(conn: sqlite3.Connection, cutoff_iso: str) -> list[sqlite3.Row]:
    return conn.execute(
        f'SELECT l.product_id AS product_id, SUM(l.quantity) AS units FROM order_lines l '
        f'JOIN orders o ON o.id = l.order_id WHERE {_ELIGIBLE} AND datetime(o.created_at) >= datetime(?) '
        f'GROUP BY l.product_id', (cutoff_iso,)).fetchall()


def purchased_product_ids(conn: sqlite3.Connection, user_id: int) -> list[str]:
    rows = conn.execute(
        f'SELECT DISTINCT l.product_id AS product_id FROM order_lines l JOIN orders o ON o.id = l.order_id '
        f"WHERE o.user_id = ? AND o.status NOT IN ({','.join(repr(v) for v in NON_REVENUE_STATUSES)}) "
        f'ORDER BY l.product_id', (user_id,)).fetchall()
    return [r['product_id'] for r in rows]


def sales_orders(conn: sqlite3.Connection, start_iso: str, end_iso: str) -> list[sqlite3.Row]:
    return conn.execute(
        f'SELECT o.id, o.created_at, o.status, o.payment_status, o.source, o.subtotal_sen, o.shipping_fee_sen, '
        f'o.total_sen FROM orders o WHERE {_ELIGIBLE} AND datetime(o.created_at) >= datetime(?) '
        f'AND datetime(o.created_at) < datetime(?) ORDER BY o.created_at, o.id', (start_iso, end_iso)).fetchall()


def sales_lines(conn: sqlite3.Connection, start_iso: str, end_iso: str) -> list[sqlite3.Row]:
    return conn.execute(
        f'SELECT l.order_id, l.product_id, l.variation_id, l.name, l.unit_price_sen, l.quantity, l.line_total_sen '
        f'FROM order_lines l JOIN orders o ON o.id = l.order_id WHERE {_ELIGIBLE} '
        f'AND datetime(o.created_at) >= datetime(?) AND datetime(o.created_at) < datetime(?) '
        f'ORDER BY l.order_id, l.id', (start_iso, end_iso)).fetchall()


def product_sale_lines(conn: sqlite3.Connection, product_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        f'SELECT o.created_at AS created_at, o.source AS source, l.quantity AS quantity FROM order_lines l '
        f'JOIN orders o ON o.id = l.order_id WHERE l.product_id = ? AND {_ELIGIBLE} ORDER BY o.created_at',
        (product_id,)).fetchall()


_UPDATABLE = ('status', 'payment_status', 'payment_provider', 'shipping_reference', 'cancel_reason', 'updated_at')


def update_order_fields(conn: sqlite3.Connection, order_id: str, **fields: Any) -> None:
    """Update whitelisted columns of one order."""
    bad = [k for k in fields if k not in _UPDATABLE]
    if bad:
        raise ValueError(f'columns not updatable: {bad}')
    sets = ', '.join(f'{k} = ?' for k in fields)
    conn.execute(f'UPDATE orders SET {sets} WHERE id = ?', [*fields.values(), order_id])


def clear_stock_restored(conn: sqlite3.Connection, order_id: str) -> None:
    """Re-arm stock restoration after stock was reserved again (payment retry)."""
    conn.execute('UPDATE orders SET stock_restored = 0, stock_restored_at = NULL WHERE id = ?', (order_id,))


def _like(text: str) -> str:
    escaped = text.lower().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


def list_orders(conn: sqlite3.Connection, *, user_id: Optional[int] = None, statuses: Optional[tuple[str, ...]] = None,
                q: Optional[str] = None, limit: int, offset: int) -> tuple[list[sqlite3.Row], int]:
    """Orders newest first with `(rows, total)`. Filters: owner, stored statuses, id/customer-name substring."""
    where, args = ['1=1'], []
    if user_id is not None:
        where.append('user_id = ?')
        args.append(user_id)
    if statuses:
        where.append(f'status IN ({",".join("?" for _ in statuses)})')
        args.extend(statuses)
    if q:
        where.append("(lower(id) LIKE ? ESCAPE '\\' OR lower(customer_name) LIKE ? ESCAPE '\\')")
        args.extend([_like(q), _like(q)])
    clause = ' AND '.join(where)
    total = conn.execute(f'SELECT COUNT(*) FROM orders WHERE {clause}', args).fetchone()[0]
    rows = conn.execute(f'SELECT * FROM orders WHERE {clause} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?',
                        [*args, limit, offset]).fetchall()
    return rows, int(total)
