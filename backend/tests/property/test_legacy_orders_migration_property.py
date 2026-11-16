"""Property 2: Legacy orders survive migration unchanged.

**Validates: Requirements 1.2**
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings, strategies as st

from app.migrations.runner import get_status, run_migrations

LEGACY_COLUMNS = (
    'id', 'checkout_id', 'secret_token', 'customer_name', 'email', 'phone',
    'delivery_address', 'payment_method', 'payment_status', 'status',
    'shipping_fee_sen', 'total_sen', 'items_json', 'tracking_number',
    'created_at', 'updated_at',
)

# Exact prototype definition from backend/server.py (mirrored by 0001_baseline.sql).
LEGACY_DDL = """
CREATE TABLE orders (
  id TEXT PRIMARY KEY, checkout_id TEXT NOT NULL UNIQUE,
  secret_token TEXT NOT NULL, customer_name TEXT NOT NULL,
  email TEXT NOT NULL, phone TEXT NOT NULL, delivery_address TEXT NOT NULL,
  payment_method TEXT NOT NULL, payment_status TEXT NOT NULL,
  status TEXT NOT NULL, shipping_fee_sen INTEGER NOT NULL,
  total_sen INTEGER NOT NULL, items_json TEXT NOT NULL,
  tracking_number TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
)
"""

# SQLite text cannot hold NUL reliably through every API; surrogates are not encodable.
_text = st.text(alphabet=st.characters(blacklist_categories=('Cs',), blacklist_characters='\x00'), max_size=40)
_int = st.integers(min_value=-(2**63), max_value=2**63 - 1)


@st.composite
def legacy_rows(draw):
    count = draw(st.integers(min_value=0, max_value=8))
    ids = draw(st.lists(_text, min_size=count, max_size=count, unique=True))
    checkouts = draw(st.lists(_text, min_size=count, max_size=count, unique=True))
    rows = []
    for order_id, checkout_id in zip(ids, checkouts):
        rows.append((
            order_id, checkout_id, draw(_text), draw(_text), draw(_text), draw(_text),
            draw(_text), draw(_text), draw(_text), draw(_text), draw(_int), draw(_int),
            draw(_text), draw(st.one_of(st.none(), _text)), draw(_text), draw(_text),
        ))
    return rows


def _snapshot(conn: sqlite3.Connection) -> list[tuple]:
    cols = ', '.join(LEGACY_COLUMNS)
    return conn.execute(f'SELECT {cols} FROM orders ORDER BY id').fetchall()


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(rows=legacy_rows())
def test_legacy_orders_survive_migration_unchanged(rows):
    with tempfile.TemporaryDirectory(prefix='legacy_orders_prop_') as tmp:
        db_path = Path(tmp) / 'prototype.sqlite3'

        # Build a prototype-era database: only the orders table, no schema_migrations.
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(LEGACY_DDL)
            placeholders = ', '.join('?' for _ in LEGACY_COLUMNS)
            conn.executemany(
                f'INSERT INTO orders ({", ".join(LEGACY_COLUMNS)}) VALUES ({placeholders})', rows
            )
            conn.commit()
            before = _snapshot(conn)
        finally:
            conn.close()

        applied = run_migrations(db_path)
        assert applied, 'expected pending migrations to be applied'
        assert get_status(db_path).pending == ()

        conn = sqlite3.connect(str(db_path))
        try:
            after = _snapshot(conn)
        finally:
            conn.close()

        assert len(after) == len(before) == len(rows)
        assert after == before
