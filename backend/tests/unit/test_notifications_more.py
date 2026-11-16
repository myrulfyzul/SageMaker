"""Additional notification endpoint cases: failure paths and edge cases (Req 17.6, 17.7, 17.8, 31.1)."""
from __future__ import annotations

import pytest

from tests.unit.test_notifications_endpoints import _seed, _user


def test_empty_list_has_zero_unread(client, settings):
    _, ch = _user(client, settings, 'customer')
    body = client.get('/api/notifications', headers=ch).json()
    assert body['items'] == [] and body['total'] == 0 and body['unreadCount'] == 0


def test_offset_pagination_returns_remaining_items(client, settings):
    cid, ch = _user(client, settings, 'customer')
    ids = _seed(settings, cid, 3)
    body = client.get('/api/notifications?limit=2&offset=2', headers=ch).json()
    assert [i['id'] for i in body['items']] == [ids[0]]
    assert body['offset'] == 2 and body['total'] == 3


@pytest.mark.parametrize('query', ['limit=0', 'limit=101', 'limit=abc', 'offset=-1'])
def test_invalid_pagination_rejected(client, settings, query):
    _, ch = _user(client, settings, 'customer')
    assert client.get(f'/api/notifications?{query}', headers=ch).status_code == 422


def test_list_never_contains_other_users_items(client, settings):
    cid, ch = _user(client, settings, 'customer')
    sid, _ = _user(client, settings, 'seller')
    _seed(settings, sid, 2)
    body = client.get('/api/notifications', headers=ch).json()
    assert body['items'] == [] and body['unreadCount'] == 0


def test_mark_one_is_idempotent(client, settings):
    cid, ch = _user(client, settings, 'customer')
    ids = _seed(settings, cid, 2)
    first = client.post(f'/api/notifications/{ids[0]}/read', headers=ch)
    second = client.post(f'/api/notifications/{ids[0]}/read', headers=ch)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {'unreadCount': 1}


def test_foreign_mark_leaves_owner_unread(client, settings):
    cid, ch = _user(client, settings, 'customer')
    sid, sh = _user(client, settings, 'seller')
    theirs = _seed(settings, sid, 1)
    assert client.post(f'/api/notifications/{theirs[0]}/read', headers=ch).status_code == 404
    items = client.get('/api/notifications', headers=sh).json()
    assert items['unreadCount'] == 1 and items['items'][0]['isRead'] is False


def test_mark_one_reflected_in_list_flag(client, settings):
    cid, ch = _user(client, settings, 'customer')
    ids = _seed(settings, cid, 1)
    client.post(f'/api/notifications/{ids[0]}/read', headers=ch)
    body = client.get('/api/notifications', headers=ch).json()
    assert body['items'][0]['isRead'] is True and body['unreadCount'] == 0


def test_read_all_with_no_notifications_and_repeat(client, settings):
    cid, ch = _user(client, settings, 'customer')
    assert client.post('/api/notifications/read-all', headers=ch).json() == {'unreadCount': 0}
    _seed(settings, cid, 2)
    assert client.post('/api/notifications/read-all', headers=ch).json() == {'unreadCount': 0}
    assert client.post('/api/notifications/read-all', headers=ch).json() == {'unreadCount': 0}


@pytest.mark.parametrize('role', ['seller', 'admin'])
def test_other_allowed_roles_can_list(client, settings, role):
    _, h = _user(client, settings, role)
    assert client.get('/api/notifications', headers=h).status_code == 200


def test_anonymous_cannot_mark(client, settings):
    assert client.post('/api/notifications/1/read').status_code == 401
    assert client.post('/api/notifications/read-all').status_code == 401


@pytest.mark.parametrize('bad', ['-1', '1.5', '%D9%A1', '0000000000000000000'])
def test_malformed_ids_give_same_404(client, settings, bad):
    _, ch = _user(client, settings, 'customer')
    expected = client.post('/api/notifications/99999/read', headers=ch)
    r = client.post(f'/api/notifications/{bad}/read', headers=ch)
    assert r.status_code == 404 and r.json() == expected.json()
