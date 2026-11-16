"""Property 30: Order creation notifications.

For any number of Staff_Users, creating an Order creates one Notification for the Customer and one for each Staff_User,
and creating a Custom_Order creates one unread Notification for each Staff_User.

**Validates: Requirements 14.8, 16.4**
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

PASSWORD = ''.join(['Secret', '123'])
_counter = itertools.count()
PROFILE = dict(max_examples=30, deadline=None, suppress_health_check=list(HealthCheck))
DELIVERY = {'name': 'Aisha Rahman', 'phone': '0123456789', 'email': 'aisha@example.com',
            'address': '12 Jalan Bukit Bintang', 'postcode': '55100', 'state': 'Kuala Lumpur'}


def _h(token):
    return {'Authorization': f'Bearer {token}'}


class _Env:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix='createnotif_'))
        self.db_path = self.dir / 't.sqlite3'
        settings = Settings(database_path=self.db_path, media_dir=self.dir / 'media', demo_mode=True)
        self.client_cm = TestClient(create_app(settings))
        self.client = self.client_cm.__enter__()
        self.sql("DELETE FROM products WHERE id = 'np1'")
        self.sql("INSERT INTO products (id, name, description, category_id, price_sen, is_active, created_at, "
                 "updated_at) VALUES ('np1', 'Notif Product', '', 1, 1000, 1, 'now', 'now')")
        self.sql('INSERT INTO stock_levels (sku_key, product_id, variation_id, quantity, opening_quantity) '
                 "VALUES ('np1', 'np1', NULL, 1000000, 1000000)")

    def sql(self, query, params=()):
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                return conn.execute(query, params).fetchall()
        finally:
            conn.close()

    def customer(self):
        email = f'c{next(_counter)}@example.com'
        self.client.post('/api/auth/register', json={'name': 'Aisha', 'email': email, 'password': PASSWORD})
        token = self.client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
        return self.sql('SELECT id FROM users WHERE email = ?', (email,))[0][0], token

    def add_staff(self, n):
        for _ in range(n):
            email = f's{next(_counter)}@example.com'
            self.client.post('/api/auth/register', json={'name': 'Staff', 'email': email, 'password': PASSWORD})
            role = 'admin' if next(_counter) % 2 else 'seller'
            self.sql('UPDATE users SET role = ? WHERE email = ?', (role, email))

    def staff_ids(self):
        return sorted(r[0] for r in self.sql("SELECT id FROM users WHERE role IN ('seller', 'admin') "
                                             'AND is_active = 1'))

    def notes(self, related_type, related_id):
        return self.sql('SELECT user_id, type, is_read FROM notifications WHERE related_type = ? AND related_id = ?',
                        (related_type, str(related_id)))

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
@given(extra_staff=st.integers(min_value=0, max_value=4))
def test_checkout_notifies_customer_and_every_staff_user(extra_staff):
    env = _get_env()
    env.add_staff(extra_staff)
    uid, token = env.customer()
    r = env.client.post('/api/cart/lines', headers=_h(token), json={'productId': 'np1', 'quantity': 1})
    assert r.status_code == 200, r.text
    r = env.client.post('/api/checkout', headers=_h(token), json={
        'idempotencyKey': f'idem-key-{next(_counter):08d}', 'delivery': DELIVERY, 'method': 'card',
        'outcome': 'success'})
    assert r.status_code == 201, r.text
    staff = env.staff_ids()
    assert len(staff) >= extra_staff
    notes = env.notes('order', r.json()['id'])
    recipients = sorted(n[0] for n in notes)
    assert recipients == sorted(staff + [uid])  # exactly one each
    assert all(n[1] == 'order' for n in notes)


@hsettings(**PROFILE)
@given(extra_staff=st.integers(min_value=0, max_value=4))
def test_custom_order_notifies_every_staff_user_unread(extra_staff):
    env = _get_env()
    env.add_staff(extra_staff)
    uid, token = env.customer()
    r = env.client.post('/api/custom-orders', headers=_h(token), data={
        'productType': 'Vase', 'description': 'A hand made ceramic vase', 'quantity': '1',
        'preferredDate': '2099-01-01'})
    assert r.status_code == 201, r.text
    staff = env.staff_ids()
    assert len(staff) >= extra_staff
    notes = env.notes('custom_order', r.json()['id'])
    staff_notes = [n for n in notes if n[0] in staff]
    assert sorted(n[0] for n in staff_notes) == staff  # exactly one per Staff_User
    assert all(n[1] == 'custom_order' and not n[2] for n in staff_notes)  # unread
