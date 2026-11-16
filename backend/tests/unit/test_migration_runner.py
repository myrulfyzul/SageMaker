"""Migration_Runner behaviour using temporary versions directories (Req 1.2-1.5)."""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.migrations import runner  # noqa: E402
from app.migrations.runner import MigrationError, get_status, run_migrations, split_statements  # noqa: E402
import migrate  # noqa: E402


def _versions(tmp_path: Path, files: dict[str, str]) -> Path:
    directory = tmp_path / 'versions'
    directory.mkdir()
    for name, body in files.items():
        (directory / name).write_text(body, encoding='utf-8')
    return directory


def _tables(db: Path) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_split_statements_handles_semicolons_in_triggers_and_comments():
    sql = (
        '-- header; comment\nCREATE TABLE a (x INTEGER);\n'
        'CREATE TRIGGER t AFTER INSERT ON a BEGIN\n  UPDATE a SET x = 1;\nEND;\n-- trailing\n'
    )
    parts = split_statements(sql)
    assert len(parts) == 3
    assert parts[1].startswith('CREATE TRIGGER') and parts[1].endswith('END;')


def test_applies_sql_and_python_in_order_and_is_idempotent(tmp_path):
    versions = _versions(tmp_path, {
        '0002_py.py': 'def up(conn):\n    conn.execute("INSERT INTO a VALUES (2)")\n',
        '0001_sql.sql': 'CREATE TABLE a (x INTEGER);\nINSERT INTO a VALUES (1);\n',
    })
    db = tmp_path / 'db.sqlite3'
    assert run_migrations(db, versions) == ['0001_sql', '0002_py']
    assert run_migrations(db, versions) == []
    conn = sqlite3.connect(db)
    assert [r[0] for r in conn.execute('SELECT x FROM a ORDER BY x')] == [1, 2]
    conn.close()
    assert get_status(db, versions).pending == ()


def test_failure_rolls_back_version_names_it_and_keeps_earlier(tmp_path):
    versions = _versions(tmp_path, {
        '0001_ok.sql': 'CREATE TABLE a (x INTEGER);',
        '0002_bad.sql': 'CREATE TABLE b (y INTEGER);\nINSERT INTO missing VALUES (1);',
        '0003_never.sql': 'CREATE TABLE c (z INTEGER);',
    })
    db = tmp_path / 'db.sqlite3'
    with pytest.raises(MigrationError) as info:
        run_migrations(db, versions)
    assert info.value.version == '0002_bad'
    assert str(info.value).startswith('Migration failed: 0002_bad: ')
    assert _tables(db) >= {'a', 'schema_migrations'}
    assert 'b' not in _tables(db) and 'c' not in _tables(db)
    assert get_status(db, versions).pending == ('0002_bad', '0003_never')


def test_python_failure_rolls_back(tmp_path):
    versions = _versions(tmp_path, {
        '0001_py.py': 'def up(conn):\n    conn.execute("CREATE TABLE a (x)")\n    raise RuntimeError("boom")\n',
    })
    db = tmp_path / 'db.sqlite3'
    with pytest.raises(MigrationError, match='0001_py: boom'):
        run_migrations(db, versions)
    assert 'a' not in _tables(db)


def test_backup_once_for_existing_database_and_not_for_fresh(tmp_path):
    versions = _versions(tmp_path, {
        '0001_a.sql': 'CREATE TABLE a (x);', '0002_b.sql': 'CREATE TABLE b (y);',
    })
    fresh = tmp_path / 'fresh.sqlite3'
    run_migrations(fresh, versions)
    assert list(tmp_path.glob('fresh.premigrate-*.bak')) == []

    existing = tmp_path / 'existing.sqlite3'
    conn = sqlite3.connect(existing)
    conn.execute('CREATE TABLE orders (id TEXT)')
    conn.commit()
    conn.close()
    original = existing.read_bytes()
    run_migrations(existing, versions)
    backups = list(tmp_path.glob('existing.premigrate-*.bak'))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    run_migrations(existing, versions)
    assert len(list(tmp_path.glob('existing.premigrate-*.bak'))) == 1


def test_lifespan_exits_1_naming_failed_version(tmp_path, monkeypatch, capsys):
    versions = _versions(tmp_path, {'0001_bad.sql': 'THIS IS NOT SQL;'})
    monkeypatch.setattr(runner, 'VERSIONS_DIR', versions)
    app = create_app(Settings(database_path=tmp_path / 'db.sqlite3'))
    async def start() -> None:
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(SystemExit) as info:
        asyncio.run(start())
    assert info.value.code == 1
    assert 'Migration failed: 0001_bad: ' in capsys.readouterr().err


def test_cli_status_and_up(tmp_path, monkeypatch, capsys):
    versions = _versions(tmp_path, {'0001_a.sql': 'CREATE TABLE a (x);'})
    monkeypatch.setattr(runner, 'VERSIONS_DIR', versions)
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'db.sqlite3'))
    assert migrate.main(['status']) == 0
    assert 'Pending: 0001_a' in capsys.readouterr().out
    assert migrate.main(['up']) == 0
    assert 'Applied: 0001_a' in capsys.readouterr().out
    assert migrate.main(['status']) == 0
    assert 'Pending: (none)' in capsys.readouterr().out
    assert migrate.main(['bogus']) == 2
