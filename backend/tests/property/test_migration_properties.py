"""Property 1: Migration atomicity and idempotence.

**Validates: Requirements 1.3, 1.4, 1.5**
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

from hypothesis import given, settings, strategies as st

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import migrate  # noqa: E402
from app.migrations import runner  # noqa: E402
from app.migrations.runner import MigrationError, run_migrations  # noqa: E402

BAD_STATEMENTS = [
    'INSERT INTO no_such_table VALUES (1);',
    'THIS IS NOT SQL;',
    'ALTER TABLE no_such_table ADD COLUMN x TEXT;',
    'CREATE TABLE schema_migrations (x INTEGER);',  # already exists
]


@st.composite
def migration_sets(draw):
    """A list of migrations, each a list of valid statements, plus an optional failure position."""
    count = draw(st.integers(min_value=1, max_value=5))
    migrations: list[list[str]] = []
    for i in range(count):
        stmts = [f'CREATE TABLE t{i} (id INTEGER PRIMARY KEY, v INTEGER NOT NULL);']
        for value in draw(st.lists(st.integers(0, 1000), max_size=3)):
            stmts.append(f'INSERT INTO t{i} (v) VALUES ({value});')
        if i > 0:  # data changes to earlier tables must also roll back
            for value in draw(st.lists(st.integers(0, 1000), max_size=2)):
                stmts.append(f'INSERT INTO t{i - 1} (v) VALUES ({value});')
        migrations.append(stmts)
    fail = draw(st.one_of(st.none(), st.tuples(
        st.integers(0, count - 1), st.integers(0, 10), st.sampled_from(BAD_STATEMENTS))))
    return migrations, fail


def _write_versions(directory: Path, migrations: list[list[str]], fail) -> list[str]:
    versions = []
    for i, stmts in enumerate(migrations):
        stmts = list(stmts)
        if fail is not None and fail[0] == i:
            stmts.insert(min(fail[1], len(stmts)), fail[2])
        version = f'{i + 1:04d}_m{i}'
        (directory / f'{version}.sql').write_text('\n'.join(stmts) + '\n', encoding='utf-8')
        versions.append(version)
    return versions


def _snapshot(db: Path):
    """Schema (sqlite_master) plus every user table's rows, excluding applied_at timestamps."""
    conn = sqlite3.connect(str(db))
    try:
        schema = conn.execute('SELECT type, name, sql FROM sqlite_master ORDER BY type, name').fetchall()
        data = {}
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'").fetchall():
            if name == 'schema_migrations':
                data[name] = conn.execute('SELECT version FROM schema_migrations ORDER BY version').fetchall()
            else:
                data[name] = conn.execute(f'SELECT * FROM "{name}" ORDER BY 1').fetchall()
        return schema, data
    finally:
        conn.close()


def _recorded(db: Path) -> list[str]:
    conn = sqlite3.connect(str(db))
    try:
        return [r[0] for r in conn.execute('SELECT version FROM schema_migrations ORDER BY version')]
    finally:
        conn.close()


@settings(max_examples=40, deadline=None)
@given(migration_sets())
def test_failed_migration_leaves_no_trace(case):
    migrations, fail = case
    if fail is None:
        return
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        versions_dir = root / 'versions'
        versions_dir.mkdir()
        versions = _write_versions(versions_dir, migrations, fail)
        failed_index = fail[0]

        # Reference: only the migrations before the failing one, applied cleanly.
        ref_versions = root / 'ref_versions'
        ref_versions.mkdir()
        _write_versions(ref_versions, migrations[:failed_index], None)
        ref_db = root / 'ref.sqlite3'
        run_migrations(ref_db, ref_versions)

        db = root / 'test.sqlite3'
        try:
            run_migrations(db, versions_dir)
            raise AssertionError('expected MigrationError')
        except MigrationError as exc:
            assert exc.version == versions[failed_index]
            assert versions[failed_index] in str(exc)

        assert _recorded(db) == versions[:failed_index]
        assert _snapshot(db) == _snapshot(ref_db)


@settings(max_examples=25, deadline=None)
@given(migration_sets(), st.integers(min_value=1, max_value=4))
def test_repeated_runs_are_idempotent(case, repeats):
    migrations, _ = case
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        versions_dir = root / 'versions'
        versions_dir.mkdir()
        versions = _write_versions(versions_dir, migrations, None)
        db = root / 'test.sqlite3'

        assert run_migrations(db, versions_dir) == versions
        first = _snapshot(db)
        for _ in range(repeats):
            assert run_migrations(db, versions_dir) == []
            assert _snapshot(db) == first
        assert _recorded(db) == versions


@settings(max_examples=10, deadline=None)
@given(migration_sets())
def test_cli_exits_one_naming_failed_version(case, ):
    migrations, fail = case
    if fail is None:
        return
    import os
    import contextlib
    import io

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        versions_dir = root / 'versions'
        versions_dir.mkdir()
        versions = _write_versions(versions_dir, migrations, fail)
        original_dir = runner.VERSIONS_DIR
        original_env = os.environ.get('DATABASE_PATH')
        runner.VERSIONS_DIR = versions_dir
        os.environ['DATABASE_PATH'] = str(root / 'cli.sqlite3')
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                code = migrate.main(['up'])
        finally:
            runner.VERSIONS_DIR = original_dir
            if original_env is None:
                os.environ.pop('DATABASE_PATH', None)
            else:
                os.environ['DATABASE_PATH'] = original_env
        assert code == 1
        assert f'Migration failed: {versions[fail[0]]}:' in err.getvalue()
