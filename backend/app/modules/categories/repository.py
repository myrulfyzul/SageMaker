"""SQL for the categories-owned table."""
from __future__ import annotations

import sqlite3


def list_all(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute('SELECT id, slug, name FROM categories ORDER BY sort_order, id').fetchall()


def exists(conn: sqlite3.Connection, category_id: int) -> bool:
    return conn.execute('SELECT 1 FROM categories WHERE id = ?', (category_id,)).fetchone() is not None


def get_many(conn: sqlite3.Connection, category_ids: list[int]) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    for start in range(0, len(category_ids), 500):  # stay under SQLite's variable limit
        chunk = category_ids[start:start + 500]
        marks = ','.join('?' * len(chunk))
        rows += conn.execute(f'SELECT id, slug, name FROM categories WHERE id IN ({marks})', chunk).fetchall()
    return rows


def ids_matching(conn: sqlite3.Connection, ref: str) -> list[int]:
    """Ids of categories whose slug equals `ref` or whose id, as text, equals `ref`."""
    return [int(r['id']) for r in conn.execute(
        'SELECT id FROM categories WHERE slug = ? OR CAST(id AS TEXT) = ?', (ref, ref)).fetchall()]


def id_by_slug(conn: sqlite3.Connection, slug: str) -> int | None:
    row = conn.execute('SELECT id FROM categories WHERE slug = ?', (slug,)).fetchone()
    return None if row is None else int(row['id'])
