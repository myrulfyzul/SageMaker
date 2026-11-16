"""SQL for the products-owned tables: products, product_variations, product_images (read side).

Every function takes the caller's open connection. All external input is bound as parameters (Req 28.7).
"""
from __future__ import annotations

import sqlite3
from typing import Optional

SORT_SQL = {'price_asc': 'p.price_sen ASC, p.name ASC, p.id ASC',
            'price_desc': 'p.price_sen DESC, p.name ASC, p.id ASC'}
DEFAULT_ORDER = 'p.name ASC, p.id ASC'

_SELECT = ('SELECT p.id, p.name, p.description, p.category_id, '
           'p.price_sen, p.artisan_id, p.made_to_order, p.is_active, p.is_demo, p.created_at '
           'FROM products p')


def escape_like(text: str) -> str:
    """Escape `\\`, `%` and `_` so the query is a literal substring (used with ESCAPE '\\')."""
    return text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _where(search: Optional[str], category_ids: Optional[list[int]]) -> tuple[str, list[object]]:
    clauses = ['p.is_active = 1']
    params: list[object] = []
    if search:
        pattern = f'%{escape_like(search.lower())}%'
        clauses.append("(lower(p.name) LIKE ? ESCAPE '\\' OR lower(p.description) LIKE ? ESCAPE '\\')")
        params += [pattern, pattern]
    if category_ids is not None:
        if category_ids:
            clauses.append(f"p.category_id IN ({','.join('?' * len(category_ids))})")
            params += category_ids
        else:
            clauses.append('0 = 1')
    return ' WHERE ' + ' AND '.join(clauses), params


def list_active(conn: sqlite3.Connection, *, search: Optional[str], category_ids: Optional[list[int]],
                sort: Optional[str], limit: int, offset: int) -> tuple[list[sqlite3.Row], int]:
    where, params = _where(search, category_ids)
    total = conn.execute(f'SELECT COUNT(*) FROM products p{where}',
                         params).fetchone()[0]
    order = SORT_SQL.get(sort or '', DEFAULT_ORDER)
    rows = conn.execute(f'{_SELECT}{where} ORDER BY {order} LIMIT ? OFFSET ?', [*params, limit, offset]).fetchall()
    return rows, int(total)


def list_for_staff(conn: sqlite3.Connection, *, search: Optional[str], category_ids: Optional[list[int]],
                   active: Optional[bool], limit: int, offset: int) -> tuple[list[sqlite3.Row], int]:
    """Staff list: active and inactive products, optional name/description search, category and active filters."""
    where, params = _where(search, category_ids)
    where = where.replace('p.is_active = 1', '1 = 1' if active is None else 'p.is_active = ?', 1)
    if active is not None:
        params.insert(0, 1 if active else 0)
    total = conn.execute(f'SELECT COUNT(*) FROM products p{where}',
                         params).fetchone()[0]
    rows = conn.execute(f'{_SELECT}{where} ORDER BY {DEFAULT_ORDER} LIMIT ? OFFSET ?', [*params, limit, offset]).fetchall()
    return rows, int(total)


def insert_product(conn: sqlite3.Connection, *, product_id: str, name: str, description: str, category_id: int,
                   price_sen: int, artisan_id: Optional[int], made_to_order: bool, now: str) -> None:
    conn.execute(
        'INSERT INTO products (id, name, description, category_id, price_sen, artisan_id, made_to_order, is_active, '
        'is_demo, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)',
        (product_id, name, description, category_id, price_sen, artisan_id, int(made_to_order), now, now))


def update_product(conn: sqlite3.Connection, product_id: str, fields: dict[str, object], now: str) -> None:
    """`fields` keys are fixed column names chosen by the service, never client input."""
    assignments = ', '.join(f'{col} = ?' for col in fields)
    conn.execute(f'UPDATE products SET {assignments}, updated_at = ? WHERE id = ?', [*fields.values(), now, product_id])


def set_active(conn: sqlite3.Connection, product_id: str, active: bool, now: str) -> None:
    conn.execute('UPDATE products SET is_active = ?, updated_at = ? WHERE id = ?', (int(active), now, product_id))


def delete_product(conn: sqlite3.Connection, product_id: str) -> list[str]:
    """Delete the product (variations and images cascade). Returns stored image file names to remove from disk."""
    files = [r['filename'] for r in conn.execute(
        'SELECT filename FROM product_images WHERE product_id = ? AND filename IS NOT NULL', (product_id,))]
    conn.execute('DELETE FROM products WHERE id = ?', (product_id,))
    return files


def insert_variation(conn: sqlite3.Connection, product_id: str, label: str, delta: int, active: bool) -> int:
    cur = conn.execute('INSERT INTO product_variations (product_id, label, price_delta_sen, is_active) VALUES (?, ?, ?, ?)',
                       (product_id, label, delta, int(active)))
    return int(cur.lastrowid)


def update_variation(conn: sqlite3.Connection, variation_id: int, label: str, delta: int, active: bool) -> None:
    conn.execute('UPDATE product_variations SET label = ?, price_delta_sen = ?, is_active = ? WHERE id = ?',
                 (label, delta, int(active), variation_id))


def all_variations(conn: sqlite3.Connection, product_id: str) -> list[sqlite3.Row]:
    return conn.execute('SELECT id, label, price_delta_sen, is_active FROM product_variations WHERE product_id = ? ORDER BY id',
                        (product_id,)).fetchall()


def insert_image(conn: sqlite3.Connection, product_id: str, filename: str) -> None:
    order = conn.execute('SELECT COALESCE(MAX(sort_order), -1) + 1 FROM product_images WHERE product_id = ?',
                         (product_id,)).fetchone()[0]
    conn.execute('INSERT INTO product_images (product_id, filename, sort_order, is_demo) VALUES (?, ?, ?, 0)',
                 (product_id, filename, order))


def get_by_id(conn: sqlite3.Connection, product_id: str) -> Optional[sqlite3.Row]:
    return conn.execute(f'{_SELECT} WHERE p.id = ?', (product_id,)).fetchone()


def variations_for(conn: sqlite3.Connection, product_ids: list[str], *, include_inactive: bool) -> dict[str, list[sqlite3.Row]]:
    return _group(conn, 'product_variations', 'id, product_id, label, price_delta_sen, is_active', product_ids,
                  'id', None if include_inactive else 'is_active = 1')


def images_for(conn: sqlite3.Connection, product_ids: list[str]) -> dict[str, list[sqlite3.Row]]:
    return _group(conn, 'product_images', 'id, product_id, filename, external_url, is_demo', product_ids,
                  'sort_order, id', None)


def _group(conn: sqlite3.Connection, table: str, columns: str, product_ids: list[str], order: str,
           extra: Optional[str]) -> dict[str, list[sqlite3.Row]]:
    grouped: dict[str, list[sqlite3.Row]] = {pid: [] for pid in product_ids}
    if not product_ids:
        return grouped
    marks = ','.join('?' * len(product_ids))
    where = f'product_id IN ({marks})' + (f' AND {extra}' if extra else '')
    for row in conn.execute(f'SELECT {columns} FROM {table} WHERE {where} ORDER BY {order}', product_ids).fetchall():
        grouped[row['product_id']].append(row)
    return grouped
