"""Migration_Runner: versioned, transactional, add-only schema migrations for SQLite.

A version is ``NNNN_name.sql`` (statements run one by one) or ``NNNN_name.py`` exposing
``up(conn)``. Each pending version runs inside its own ``BEGIN IMMEDIATE`` transaction together
with its ``schema_migrations`` row, so a failure rolls the version back completely.
"""
from __future__ import annotations

import importlib.util
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

VERSIONS_DIR = Path(__file__).resolve().parent / 'versions'
SUPPORTED_SUFFIXES = ('.sql', '.py')


class MigrationError(Exception):
    """A migration failed; ``version`` names the failed version and the cause is in the message."""

    def __init__(self, version: str, cause: object):
        self.version = version
        self.cause = str(cause)
        super().__init__(f'Migration failed: {version}: {self.cause}')


@dataclass(frozen=True)
class MigrationFile:
    version: str
    path: Path


@dataclass(frozen=True)
class MigrationStatus:
    applied: tuple[str, ...]
    pending: tuple[str, ...]


def list_versions(versions_dir: Union[str, Path, None] = None) -> list[MigrationFile]:
    """Version files on disk, sorted by version id. A missing directory means no versions."""
    directory = Path(versions_dir) if versions_dir is not None else VERSIONS_DIR
    if not directory.is_dir():
        return []
    found: dict[str, MigrationFile] = {}
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix not in SUPPORTED_SUFFIXES or path.name.startswith('_'):
            continue
        if path.stem in found:
            raise MigrationError(path.stem, f'duplicate version files {found[path.stem].path.name} and {path.name}')
        found[path.stem] = MigrationFile(path.stem, path)
    return [found[key] for key in sorted(found)]


def split_statements(sql: str) -> list[str]:
    """Split SQL text into complete statements using ``sqlite3.complete_statement``."""
    statements: list[str] = []
    buffer = ''
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ''
    if buffer.strip():
        # Trailing comment-only text is harmless; an unfinished statement fails when executed.
        statements.append(buffer.strip() + '\n;')
    return statements


def _has_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'").fetchone()
    return row is not None


def _bootstrap(conn: sqlite3.Connection) -> None:
    conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')


def _applied(conn: sqlite3.Connection) -> list[str]:
    if not _has_table(conn):
        return []
    return [row[0] for row in conn.execute('SELECT version FROM schema_migrations ORDER BY version')]


def _backup(db_path: Path) -> Optional[Path]:
    """Byte-for-byte copy of an existing, non-empty database file. Returns None if there is nothing to copy."""
    if not db_path.is_file() or db_path.stat().st_size == 0:
        return None
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    target = db_path.with_name(f'{db_path.stem}.premigrate-{stamp}.bak')
    shutil.copyfile(db_path, target)
    return target


def _run_sql(conn: sqlite3.Connection, path: Path) -> None:
    for statement in split_statements(path.read_text(encoding='utf-8')):
        conn.execute(statement)


def _run_python(conn: sqlite3.Connection, version: str, path: Path) -> None:
    spec = importlib.util.spec_from_file_location(f'_sagemaker_migration_{version}', path)
    if spec is None or spec.loader is None:
        raise ImportError(f'cannot load {path.name}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    up = getattr(module, 'up', None)
    if not callable(up):
        raise AttributeError(f'{path.name} does not define up(conn)')
    up(conn)


def _apply(conn: sqlite3.Connection, migration: MigrationFile) -> None:
    conn.execute('BEGIN IMMEDIATE')
    try:
        if migration.path.suffix == '.sql':
            _run_sql(conn, migration.path)
        else:
            _run_python(conn, migration.version, migration.path)
        conn.execute(
            'INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)',
            (migration.version, datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')),
        )
        conn.execute('COMMIT')
    except BaseException as exc:
        if conn.in_transaction:
            conn.execute('ROLLBACK')
        if isinstance(exc, Exception):
            raise MigrationError(migration.version, exc) from exc
        raise


def _open(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None, timeout=5.0)
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def get_status(db_path: Union[str, Path], versions_dir: Union[str, Path, None] = None) -> MigrationStatus:
    """Applied and pending versions. Never writes to the database."""
    path = Path(db_path)
    on_disk = [m.version for m in list_versions(versions_dir)]
    applied: list[str] = []
    if path.is_file() and path.stat().st_size > 0:
        conn = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True, isolation_level=None)
        try:
            applied = _applied(conn)
        finally:
            conn.close()
    pending = [v for v in on_disk if v not in set(applied)]
    return MigrationStatus(tuple(applied), tuple(pending))


def run_migrations(db_path: Union[str, Path], versions_dir: Union[str, Path, None] = None) -> list[str]:
    """Apply every pending version in order. Returns the versions applied by this call.

    Raises MigrationError naming the failed version; earlier versions stay committed.
    """
    path = Path(db_path)
    migrations = list_versions(versions_dir)
    conn = _open(path)
    try:
        applied = set(_applied(conn))
        pending = [m for m in migrations if m.version not in applied]
        if not pending:
            _bootstrap(conn)
            return []
        # One backup per run, taken before anything (including the bootstrap) touches the file.
        _backup(path)
        _bootstrap(conn)
        done: list[str] = []
        for migration in pending:
            _apply(conn, migration)
            done.append(migration.version)
        return done
    finally:
        conn.close()
