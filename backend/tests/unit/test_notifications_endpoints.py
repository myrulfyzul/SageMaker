"""Notifications endpoints: own-only listing, read flags, role exclusion, identical 404s (Req 17.6 to 17.8)."""
from __future__ import annotations

from app import db
from app.modules.notifications import api as notif
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])


def _user(client, settings, role):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        uid = users_api.create_user(conn, name='U', email=f'{role}@example.com',
                                    password_hash=hash_password(PASSWORD), role=role)['id']
    conn.close()
    token = client.post('/api/auth/login', json={'email': f'{role}@example.com', 'password': PASSWORD}).json()['token']
    return uid, {'Authorization': f'Bearer {token}'}


def _seed(settings, user_id, n):
    conn = db.connect(settings.database_path)
    with db.transaction(conn):
        ids = [notif.create(conn, user_id, 'system', f't{i}', 'b') for i in range(n)]
    conn.close()
    return ids


def test_list_own_newest_first_paginated_and_mark_read(client, settings):
    cid, ch = _user(client, settings, 'customer')
    sid, sh = _user(client, settings, 'seller')
    mine = _seed(settings, cid, 3)
    theirs = _seed(settings, sid, 2)

    body = client.get('/api/notifications?limit=2', headers=ch).json()
    assert [i['id'] for i in body['items']] == [mine[2], mine[1]]
    assert body['total'] == 3 and body['unreadCount'] == 3 and body['limit'] == 2

    r = client.post(f'/api/notifications/{mine[2]}/read', headers=ch)
    assert r.status_code == 200 and r.json() == {'unreadCount': 2}
    assert client.get('/api/notifications', headers=sh).json()['unreadCount'] == 2

    # Foreign and missing ids give identical 404s and change nothing.
    foreign = client.post(f'/api/notifications/{theirs[0]}/read', headers=ch)
    missing = client.post('/api/notifications/99999/read', headers=ch)
    junk = client.post('/api/notifications/abc/read', headers=ch)
    assert foreign.status_code == missing.status_code == junk.status_code == 404
    assert foreign.json() == missing.json() == junk.json()
    assert client.get('/api/notifications', headers=sh).json()['unreadCount'] == 2

    assert client.post('/api/notifications/read-all', headers=ch).json() == {'unreadCount': 0}
    assert client.get('/api/notifications', headers=sh).json()['unreadCount'] == 2


def test_artisan_forbidden_and_anonymous_unauthenticated(client, settings):
    _, ah = _user(client, settings, 'artisan')
    assert client.get('/api/notifications', headers=ah).status_code == 403
    assert client.post('/api/notifications/read-all', headers=ah).status_code == 403
    assert client.post('/api/notifications/1/read', headers=ah).status_code == 403
    assert client.get('/api/notifications').status_code == 401
