"""Notifications core: create validation, status-change dedupe, staff fan-out, low-stock skip rule."""
from __future__ import annotations

import pytest

from app import db
from app.errors import ValidationFailed
from app.migrations.runner import run_migrations
from app.modules.notifications import api as notif
from app.modules.users import api as users_api


@pytest.fixture()
def conn(tmp_path):
    path = tmp_path / 'n.sqlite3'
    run_migrations(path)
    c = db.connect(path)
    yield c
    c.close()


_HASH = 'hash-' + 'placeholder'


def _user(conn, email, role):
    return users_api.create_user(conn, name=email, email=email, password_hash=_HASH, role=role)['id']


def _rows(conn, user_id, type_=None):
    q = 'SELECT * FROM notifications WHERE user_id = ?' + (' AND type = ?' if type_ else '')
    return conn.execute(q, (user_id, type_) if type_ else (user_id,)).fetchall()


def test_create_validates_and_clips(conn):
    cust = _user(conn, 'c@x.com', 'customer')
    nid = notif.create(conn, cust, 'system', 't' * 150, 'b' * 600)
    row = conn.execute('SELECT * FROM notifications WHERE id = ?', (nid,)).fetchone()
    assert len(row['title']) == 100 and len(row['body']) == 500 and row['is_read'] == 0
    with pytest.raises(ValidationFailed):
        notif.create(conn, cust, 'bogus', 't', 'b')
    with pytest.raises(ValidationFailed):
        notif.create(conn, cust, 'system', '  ', 'b')


def test_status_change_notifies_once_and_not_when_unchanged(conn):
    cust = _user(conn, 'c@x.com', 'customer')
    assert notif.order_status_changed(conn, 'SM-1', cust, 'placed', 'placed') is None
    assert notif.order_status_changed(conn, 'SM-1', cust, 'placed', 'confirmed') is not None
    assert notif.custom_order_status_changed(conn, 'CO-1', cust, 'submitted', 'submitted') is None
    assert notif.custom_order_status_changed(conn, 'CO-1', cust, 'submitted', 'accepted') is not None
    assert len(_rows(conn, cust, 'order')) == 1 and len(_rows(conn, cust, 'custom_order')) == 1
    assert _rows(conn, cust, 'order')[0]['related_id'] == 'SM-1'


def test_created_helpers_reach_customer_and_staff_only(conn):
    cust = _user(conn, 'c@x.com', 'customer')
    seller = _user(conn, 's@x.com', 'seller')
    admin = _user(conn, 'a@x.com', 'admin')
    artisan = _user(conn, 'r@x.com', 'artisan')
    notif.order_created(conn, 'SM-1', cust)
    notif.custom_order_created(conn, 'CO-1', cust)
    notif.production_ready(conn, 7)
    assert len(_rows(conn, cust)) == 2
    assert len(_rows(conn, seller)) == 3 and len(_rows(conn, admin)) == 3
    assert _rows(conn, artisan) == []


def test_low_stock_skips_staff_with_unread_for_same_product(conn):
    seller = _user(conn, 's@x.com', 'seller')
    admin = _user(conn, 'a@x.com', 'admin')
    assert len(notif.low_stock(conn, 'p1')) == 2
    assert notif.low_stock(conn, 'p1') == []
    assert len(notif.low_stock(conn, 'p2')) == 2
    conn.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ? AND related_id = ?', (seller, 'p1'))
    assert len(notif.low_stock(conn, 'p1')) == 1
    assert len(_rows(conn, seller, 'low_stock')) == 3  # p1 (read), p2, p1 again
    assert len(_rows(conn, admin, 'low_stock')) == 2  # p1, p2 (no duplicate p1)
