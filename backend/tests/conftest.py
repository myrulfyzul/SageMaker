"""Shared fixtures: a temporary database per test run, deleted at teardown."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope='session')
def tmp_run_dir():
    path = Path(tempfile.mkdtemp(prefix='sagemaker_tests_'))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture()
def settings(tmp_run_dir, tmp_path_factory):
    db_dir = Path(tempfile.mkdtemp(dir=tmp_run_dir))
    return Settings(database_path=db_dir / 'test.sqlite3', media_dir=db_dir / 'media', demo_mode=True)


@pytest.fixture()
def app(settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
