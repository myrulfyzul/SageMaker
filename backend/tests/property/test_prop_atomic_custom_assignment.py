"""Property 50: Atomic order creation (custom-order assignment part).

A single failure injected at any step of artisan assignment (after that step's own writes have been made) leaves
neither the assignment nor a Production_Job behind; without a failure both exist, exactly once.

**Validates: Requirements 25.7, 25.8**
"""
from __future__ import annotations

import itertools
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app
from app.modules.custom_orders import repository as co_repo
from app.modules.custom_orders import service

PASSWORD = ''.join(['Secret', '123'])
_counter = itertools.count()
PROFILE = dict(max_examples=30, deadline=None, suppress_health_check=list(HealthCheck))

# step name -> (module object, attribute name) whose real effect is performed and then made to fail
STEPS = {
    'artisan_check': (service.artisans_api, 'is_active'),
    'job_create': (service.production_api, 'create_job_for_custom_order'),
    'assignment': (service.repo, 'set_assignment'),
}
PRE_COMMIT_STEPS = sorted(STEPS)

TABLES = ['custom_orders', 'production_jobs', 'production_progress', 'notifications']


class Injected(RuntimeError):
    pass


@pytest.fixture(scope='module')
def env():
    d = Path(tempfile.mkdtemp(prefix='atomic_custom_'))
    settings = Settings(database_path=d / 't.sqlite3', media_dir=d / 'media', demo_mode=True)
    cm = TestClient(create_app(settings))
    client = cm.__enter__()
    email = 'custom-owner@example.com'
    client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
    conn = db.connect(settings.database_path)
    uid = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()[0]
    with db.transaction(conn):
        conn.execute("INSERT INTO artisans (name, specialisation, availability, is_active, created_at, updated_at) "
                     "VALUES ('Siti', 'Weaving', 'available', 1, 'now', 'now')")
    artisan_id = conn.execute('SELECT id FROM artisans').fetchone()[0]
    conn.close()
    yield settings, uid, artisan_id
    cm.__exit__(None, None, None)
    shutil.rmtree(d, ignore_errors=True)


def _state(conn):
    snap = {t: [tuple(r) for r in conn.execute(f'SELECT * FROM {t} ORDER BY 1').fetchall()] for t in TABLES}
    return snap


def _new_accepted(conn, uid, qty):
    with db.transaction(conn):
        cid = co_repo.insert(conn, uid, 'Bag', 'A custom woven bag order', qty, '2099-01-01', 0, 'now')
        co_repo.set_accepted(conn, cid, 5000, 'now')
    return cid


def _failing(module, name):
    real = getattr(module, name)

    def wrapper(*args, **kwargs):
        real(*args, **kwargs)  # perform the step's real writes, then fail before commit
        raise Injected(name)
    return mock.patch.object(module, name, wrapper)


@hsettings(**PROFILE)
@given(step=st.sampled_from(PRE_COMMIT_STEPS), qty=st.integers(min_value=1, max_value=500))
def test_single_failure_at_any_step_persists_neither_assignment_nor_job(env, step, qty):
    settings, uid, artisan_id = env
    conn = db.connect(settings.database_path)
    try:
        cid = _new_accepted(conn, uid, qty)
        before = _state(conn)
        with _failing(*STEPS[step]), pytest.raises(Injected):
            service.assign_artisan(conn, cid, artisan_id)
        assert not conn.in_transaction
        assert _state(conn) == before
        row = co_repo.get(conn, cid)
        assert row['artisan_id'] is None and row['production_job_id'] is None
        assert conn.execute('SELECT COUNT(*) FROM production_jobs WHERE custom_order_id = ?',
                            (cid,)).fetchone()[0] == 0
        # the order is still assignable, and success persists both together, exactly once
        dto = service.assign_artisan(conn, cid, artisan_id)
        assert dto['artisanId'] == artisan_id and dto['productionJobId'] is not None
        assert conn.execute('SELECT COUNT(*) FROM production_jobs WHERE custom_order_id = ?',
                            (cid,)).fetchone()[0] == 1
    finally:
        conn.close()
