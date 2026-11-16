"""Seed_Script: counts, idempotent refusal, rollback on injected failure, preserved legacy orders (Req 29)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import seed  # noqa: E402
from app.db import connect  # noqa: E402

NOW = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
LEGACY_BODY = {'checkout_id': 'legacy-seed-0001', 'customer_name': 'Demo Buyer', 'email': 'demo@example.com',
               'phone': '0123456789', 'delivery_address': '123 Sample Street, Sample City',
               'payment_method': 'demo_card', 'items': [{'product_id': 'fishing', 'quantity': 2}]}
BUNDLED = {'fishing', 'hikayat', 'pouch', 'jendela'}


@pytest.fixture()
def env(settings):
    return {'DATABASE_PATH': str(settings.database_path)}


def _run(env, *args, answer='', now=NOW):
    return seed.main(list(args), environ=env, input_fn=lambda _prompt: answer, now=now)


def _one(settings, sql, params=()):
    conn = connect(settings.database_path)
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


def _table_counts(settings):
    conn = connect(settings.database_path)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {n: conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
    finally:
        conn.close()


def test_seed_creates_expected_counts(settings, env, capsys):
    assert _run(env) == seed.EXIT_OK
    assert _one(settings, 'SELECT COUNT(*) FROM products') >= 15
    assert BUNDLED <= {r for r in _ids(settings, 'SELECT id FROM products')}
    assert _one(settings, "SELECT COUNT(*) FROM users WHERE role='customer' AND is_demo=1") == 3
    for role in ('seller', 'admin', 'artisan'):
        assert _one(settings, 'SELECT COUNT(*) FROM users WHERE role=? AND is_demo=1', (role,)) == 1
    assert _one(settings, 'SELECT COUNT(*) FROM artisans WHERE is_demo=1') == 4
    assert _one(settings, 'SELECT COUNT(*) FROM custom_orders WHERE is_demo=1') >= 1
    assert _one(settings, 'SELECT COUNT(*) FROM notifications WHERE is_demo=1') >= 3
    statuses = set(_ids(settings, "SELECT DISTINCT status FROM orders WHERE source='app'"))
    assert statuses == set(seed.TIMELINE)
    assert len(set(_ids(settings, 'SELECT DISTINCT status FROM production_jobs'))) == len(seed.JOBS)
    assert _one(settings, 'SELECT COUNT(*) FROM stock_adjustments') == 0  # opening stock has no ledger rows
    assert 'Seeded demo data' in capsys.readouterr().out


def _ids(settings, sql):
    conn = connect(settings.database_path)
    try:
        return [r[0] for r in conn.execute(sql)]
    finally:
        conn.close()


def test_stock_mix_and_category_coverage(settings, env):
    assert _run(env) == seed.EXIT_OK
    conn = connect(settings.database_path)
    try:
        rows = conn.execute(
            'SELECT s.quantity, COALESCE(i.low_stock_threshold, 5) AS t FROM stock_levels s '
            'LEFT JOIN inventory_settings i ON i.product_id = s.product_id').fetchall()
        low = [r for r in rows if r['quantity'] <= r['t']]
        assert len(low) >= 2 and len(rows) - len(low) >= 5
        per_category = conn.execute('SELECT category_id, COUNT(*) FROM products GROUP BY category_id').fetchall()
        assert all(r[1] >= 2 for r in per_category if r[0] in {
            c['id'] for c in conn.execute("SELECT id FROM categories WHERE slug IN ('tote-bags','toys','gifts','accessories')")})
    finally:
        conn.close()


def test_twelve_consecutive_months_of_synthetic_sales(settings, env):
    assert _run(env) == seed.EXIT_OK
    months = _ids(settings, "SELECT DISTINCT substr(created_at, 1, 7) FROM orders WHERE source='synthetic' ORDER BY 1")
    assert months == [f'2024-{m:02d}' for m in range(7, 13)] + [f'2025-{m:02d}' for m in range(1, 7)]


def test_every_seeded_record_is_demo(settings, env):
    assert _run(env) == seed.EXIT_OK
    for table in ('users', 'artisans', 'products', 'orders', 'production_jobs', 'custom_orders'):
        assert _one(settings, f'SELECT COUNT(*) FROM {table} WHERE is_demo = 0') == 0


def test_second_run_refuses_and_changes_nothing(settings, env, capsys):
    assert _run(env) == seed.EXIT_OK
    before = _table_counts(settings)
    capsys.readouterr()
    assert _run(env) == seed.EXIT_EXISTS
    assert 'Seeded data already exists' in capsys.readouterr().err
    assert _table_counts(settings) == before


def test_failure_rolls_back_everything(settings, env, monkeypatch, capsys):
    def boom(*_a, **_k):
        raise RuntimeError('injected failure')

    monkeypatch.setattr(seed, '_seed_notifications', boom)
    assert _run(env) == seed.EXIT_FAILED
    assert 'injected failure' in capsys.readouterr().err
    assert _one(settings, 'SELECT COUNT(*) FROM users') == 0
    assert _one(settings, "SELECT COUNT(*) FROM orders WHERE source='synthetic'") == 0
    assert _one(settings, 'SELECT COUNT(*) FROM artisans') == 0
    monkeypatch.undo()
    assert _run(env) == seed.EXIT_OK  # a clean retry works


def test_reset_with_wrong_word_changes_nothing(settings, env, capsys):
    assert _run(env) == seed.EXIT_OK
    before = _table_counts(settings)
    capsys.readouterr()
    assert _run(env, '--reset', answer='reset-demo') == seed.EXIT_CANCELLED
    assert 'Reset cancelled' in capsys.readouterr().err
    assert _table_counts(settings) == before


def test_reset_with_exact_word_reseeds_and_keeps_legacy_orders(settings, env, client):
    client.get('/api/legacy/products')
    res = client.post('/api/legacy/orders', json=LEGACY_BODY)
    assert res.status_code == 201, res.text
    legacy_id = res.json()['id']
    assert _run(env) == seed.EXIT_OK
    synthetic_ids = set(_ids(settings, "SELECT id FROM orders WHERE source='synthetic'"))
    assert _run(env, '--reset', answer=seed.RESET_WORD) == seed.EXIT_OK
    assert _one(settings, "SELECT COUNT(*) FROM orders WHERE id=? AND source='legacy'", (legacy_id,)) == 1
    assert _one(settings, 'SELECT COUNT(*) FROM order_lines WHERE order_id=?', (legacy_id,)) == 1
    assert _one(settings, "SELECT quantity FROM stock_levels WHERE sku_key='fishing'") == 98  # legacy hold kept
    assert BUNDLED <= set(_ids(settings, 'SELECT id FROM products'))
    assert _one(settings, 'SELECT COUNT(*) FROM users WHERE is_demo=1') == 6  # re-seeded, not duplicated
    assert _one(settings, "SELECT COUNT(*) FROM orders WHERE source='synthetic'") == len(synthetic_ids)
    assert _run(env) == seed.EXIT_EXISTS


def test_passwords_come_from_environment_or_documented_default(settings, env):
    override = ''.join(['Chosen', 'Pw', '42x'])
    env = dict(env, DEMO_ADMIN_PASSWORD=override)
    assert _run(env) == seed.EXIT_OK
    from app.security import verify_password
    conn = connect(settings.database_path)
    try:
        admin = conn.execute("SELECT password_hash FROM users WHERE role='admin'").fetchone()[0]
        seller = conn.execute("SELECT password_hash FROM users WHERE role='seller'").fetchone()[0]
    finally:
        conn.close()
    assert verify_password(override, admin)
    assert verify_password(seed.demo_password({}, 'DEMO_SELLER_PASSWORD', seed.ACCOUNTS[3][6]), seller)


def test_bad_arguments_and_missing_database_path(env):
    assert seed.main(['--nope'], environ=env) == seed.EXIT_FAILED
    assert seed.main([], environ={}) == seed.EXIT_FAILED
