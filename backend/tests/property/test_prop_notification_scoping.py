"""Property 29: Notification scoping and low-stock de-duplication.

For any Users and Notifications, marking one or all as read changes only the targeted Notifications of the calling
User and returns the correct unread count; and for any sequence of stock changes and reads, a Staff_User receives a
new low-stock Notification for a Product only when that user has no unread low-stock Notification for that Product.

**Validates: Requirements 17.5, 17.7**
"""
from __future__ import annotations

import itertools
import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app
from app.modules.notifications import api as notifications_api

PASSWORD = ''.join(['Secret', '123'])
_counter = itertools.count()
PROFILE = dict(max_examples=40, deadline=None, suppress_health_check=list(HealthCheck))


def _h(token):
    return {'Authorization': f'Bearer {token}'}


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='notescope_'))
        self.db_path = self.dir / 't.sqlite3'
        settings = Settings(database_path=self.db_path, media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(settings))
        self.client = self.client_cm.__enter__()

    def sql(self, query, params=()):
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                return conn.execute(query, params).fetchall()
        finally:
            conn.close()

    def user(self, role='customer'):
        email = f'n{next(_counter)}@example.com'
        self.client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
        if role != 'customer':
            self.sql('UPDATE users SET role = ? WHERE email = ?', (role, email))
        token = self.client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
        return self.sql('SELECT id FROM users WHERE email = ?', (email,))[0][0], token

    def add_notes(self, user_id, n):
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                return [notifications_api.create(conn, user_id, 'system', f'Title {i}', 'Body') for i in range(n)]
        finally:
            conn.close()

    def flags(self):
        return dict(self.sql('SELECT id, is_read FROM notifications'))

    def unread(self, user_id):
        return self.sql('SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0', (user_id,))[0][0]

    def close(self):
        self.client_cm.__exit__(None, None, None)
        shutil.rmtree(self.dir, ignore_errors=True)


_env: _Env | None = None


def _get_env() -> _Env:
    global _env
    if _env is None:
        _env = _Env()
    return _env


def teardown_module(_module):
    global _env
    if _env is not None:
        _env.close()
        _env = None


@hsettings(**PROFILE)
@given(counts=st.lists(st.integers(0, 4), min_size=2, max_size=3),
       ops=st.lists(st.tuples(st.integers(0, 2), st.booleans(), st.integers(0, 12)), min_size=1, max_size=8))
def test_mark_read_only_touches_the_callers_notifications(counts, ops):
    env = _get_env()
    users = [env.user() for _ in counts]
    ids = {uid: env.add_notes(uid, n) for (uid, _), n in zip(users, counts)}
    all_ids = [i for v in ids.values() for i in v]
    for who, mark_all, pick in ops:
        who %= len(users)
        uid, token = users[who]
        before = env.flags()
        if mark_all:
            r = env.client.post('/api/notifications/read-all', headers=_h(token))
            assert r.status_code == 200, r.text
            expected = {i: (1 if i in ids[uid] else v) for i, v in before.items()}
        elif all_ids:
            target = all_ids[pick % len(all_ids)]
            r = env.client.post(f'/api/notifications/{target}/read', headers=_h(token))
            if target in ids[uid]:
                assert r.status_code == 200, r.text
                expected = {**before, target: 1}
            else:
                assert r.status_code == 404, r.text
                expected = before
        else:
            continue
        assert env.flags() == expected
        if r.status_code == 200:
            assert r.json()['unreadCount'] == env.unread(uid)
        listing = env.client.get('/api/notifications', headers=_h(token)).json()
        assert listing['unreadCount'] == env.unread(uid)


@hsettings(**PROFILE)
@given(st.lists(st.tuples(st.sampled_from(['low', 'read_all', 'read_one']), st.sampled_from(['pa', 'pb'])),
                min_size=1, max_size=15))
def test_low_stock_only_when_no_unread_for_that_product(events):
    env = _get_env()
    staff = [env.user('seller')[0] for _ in range(2)]
    for pid in ('pa', 'pb'):
        env.sql("DELETE FROM notifications WHERE type = 'low_stock' AND related_id = ?", (pid,))
    for kind, pid in events:
        conn = db.connect(env.db_path)
        try:
            if kind == 'low':
                with db.transaction(conn):
                    unread_before = {r[0] for r in conn.execute(
                        "SELECT user_id FROM notifications WHERE type = 'low_stock' AND related_id = ? "
                        'AND is_read = 0', (pid,))}
                    count_before = conn.execute(
                        "SELECT COUNT(*) FROM notifications WHERE type = 'low_stock' AND related_id = ?",
                        (pid,)).fetchone()[0]
                    created = notifications_api.low_stock(conn, pid, pid)
                    recipients = [r[0] for r in conn.execute(
                        f'SELECT user_id FROM notifications WHERE id IN ({",".join("?" * len(created))})',
                        created)] if created else []
                    count_after = conn.execute(
                        "SELECT COUNT(*) FROM notifications WHERE type = 'low_stock' AND related_id = ?",
                        (pid,)).fetchone()[0]
                # Only staff without an unread row get a new one, and each gets exactly one.
                all_staff = {r[0] for r in conn.execute(
                    "SELECT id FROM users WHERE role IN ('seller','admin','staff')")}
                assert sorted(recipients) == sorted(all_staff - unread_before)
                assert len(recipients) == len(set(recipients))
                assert set(staff) - unread_before <= set(recipients)
                assert count_after == count_before + len(recipients)
            elif kind == 'read_all':
                with db.transaction(conn):
                    conn.execute("UPDATE notifications SET is_read = 1 WHERE type = 'low_stock' "
                                 'AND related_id = ?', (pid,))
            else:
                with db.transaction(conn):
                    conn.execute("UPDATE notifications SET is_read = 1 WHERE id = (SELECT MIN(id) FROM "
                                 "notifications WHERE type = 'low_stock' AND related_id = ? AND is_read = 0)",
                                 (pid,))
        finally:
            conn.close()
