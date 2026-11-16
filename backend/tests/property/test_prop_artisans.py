"""Property 49 (artisan privacy and counts) and Property 52 (artisan part: validators).

**Validates: Requirements 23.1, 23.2, 23.3, 23.4, 23.5, 23.6**

Property 49: the public serialisation holds only public name, specialisation and story; the staff serialisation adds
private contact, assigned products and open/completed job counts equal to the job data; setting an artisan with open
jobs to `unavailable` succeeds and warns with exactly those job ids. Private contact values never appear in logs.
Property 52: create/update succeeds and reads back the same values iff every field is in range; otherwise 422
identifies each invalid field and data is unchanged.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app import db
from app.config import Settings
from app.main import create_app
from app.modules.users import api as users_api
from app.security import hash_password

PASSWORD = ''.join(['Secret', '123'])
OPEN = ('order_confirmed', 'production_assigned', 'in_production', 'quality_checking')
DONE = ('completed', 'ready_for_fulfilment')
AVAIL = ('available', 'busy', 'unavailable')
PRIVATE_KEYS = {'phone', 'email', 'address', 'privateContact', 'availability', 'openJobCount',
                'completedJobCount', 'assignedProducts', 'isActive', 'name'}

_ALPHA = st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))
settings_hs = dict(max_examples=40, deadline=None,
                   suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(self.format(record))


@pytest.fixture(scope='module')
def env():
    with tempfile.TemporaryDirectory(prefix='artisan_prop_') as d:
        cfg = Settings(database_path=Path(d) / 't.sqlite3', media_dir=Path(d) / 'media', demo_mode=True)
        app = create_app(cfg)
        capture = _Capture()
        root = logging.getLogger()
        root.addHandler(capture)
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                conn = db.connect(cfg.database_path)
                with db.transaction(conn):
                    users_api.create_user(conn, name='S', email='seller@example.com',
                                          password_hash=hash_password(PASSWORD), role='seller')
                    users_api.create_user(conn, name='C', email='cust@example.com',
                                          password_hash=hash_password(PASSWORD), role='customer')
                conn.close()

                def hdr(email):
                    t = client.post('/api/auth/login', json={'email': email, 'password': PASSWORD}).json()['token']
                    return {'Authorization': f'Bearer {t}'}

                yield client, hdr('seller@example.com'), hdr('cust@example.com'), cfg, capture
        finally:
            root.removeHandler(capture)


def _insert_jobs(cfg, artisan_id, statuses):
    conn = db.connect(cfg.database_path)
    ids = []
    with db.transaction(conn):
        for s in statuses:
            cur = conn.execute(
                'INSERT INTO production_jobs (artisan_id, quantity, status, created_at, updated_at) '
                "VALUES (?, 1, ?, '2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z')", (artisan_id, s))
            ids.append(int(cur.lastrowid))
    conn.close()
    return ids


def _list_total(client, headers):
    return client.get('/api/staff/artisans', headers=headers, params={'limit': 1}).json()['total']


texts = st.text(_ALPHA, min_size=1, max_size=100)
stories = st.text(_ALPHA, max_size=200)
phones = st.from_regex(r'\+60[0-9]{9}', fullmatch=True)
emails = st.from_regex(r'[a-z]{5,10}[0-9]{3}@priv\.example\.com', fullmatch=True)
addresses = st.from_regex(r'[0-9]{2} Secretlane[A-Za-z]{4,8}', fullmatch=True)


@hsettings(**settings_hs)
@given(name=texts, spec=texts, story=stories, phone=phones, email=emails, address=addresses,
       availability=st.sampled_from(AVAIL),
       open_statuses=st.lists(st.sampled_from(OPEN), max_size=4),
       done_statuses=st.lists(st.sampled_from(DONE), max_size=4))
def test_privacy_counts_and_warning(env, name, spec, story, phone, email, address, availability,
                                    open_statuses, done_statuses):
    client, staff, customer, cfg, capture = env
    capture.lines.clear()
    r = client.post('/api/staff/artisans', headers=staff, json={
        'name': name, 'specialisation': spec, 'availability': availability, 'story': story,
        'phone': phone, 'email': email, 'address': address})
    assert r.status_code == 201
    aid = r.json()['id']
    open_ids = _insert_jobs(cfg, aid, open_statuses)
    _insert_jobs(cfg, aid, done_statuses)

    # staff view: private contact + counts equal the job data
    s = client.get(f'/api/staff/artisans/{aid}', headers=staff).json()
    assert s['privateContact'] == {'phone': phone, 'email': email, 'address': address}
    assert s['openJobCount'] == len(open_statuses) and s['completedJobCount'] == len(done_statuses)
    assert isinstance(s['assignedProducts'], list)

    # public view: only id, public name, specialisation and story; no private values anywhere
    for headers in ({}, customer):
        p = client.get(f'/api/artisans/{aid}', headers=headers)
        assert p.status_code == 200
        body = p.json()
        assert set(body) == {'id', 'publicName', 'specialisation', 'story'}
        assert body['publicName'] == name.strip() and body['specialisation'] == spec.strip()
        assert body['story'] == story
        for secret in (phone, email, address):
            assert secret not in p.text
        lst = client.get('/api/artisans', headers=headers, params={'limit': 100})
        assert lst.status_code == 200
        for secret in (phone, email, address):
            assert secret not in lst.text

    # contact endpoints are denied to customers and visitors (Req 23.8)
    for headers, code in ((customer, 403), ({}, 401)):
        for path in (f'/api/staff/artisans/{aid}', '/api/staff/artisans'):
            d = client.get(path, headers=headers)
            assert d.status_code == code
            for secret in (phone, email, address):
                assert secret not in d.text

    # unavailable with open jobs: saved, with a warning listing exactly the open job ids
    u = client.put(f'/api/staff/artisans/{aid}', headers=staff, json={
        'name': name, 'specialisation': spec, 'availability': 'unavailable'})
    assert u.status_code == 200
    ub = u.json()
    assert ub['availability'] == 'unavailable'
    if open_ids:
        assert len(ub['warnings']) == 1 and sorted(ub['warnings'][0]['jobIds']) == open_ids
    else:
        assert ub['warnings'] == []
    # contact preserved when omitted on edit
    assert ub['privateContact']['phone'] == phone

    # private contact values never appear in logs
    joined = '\n'.join(capture.lines)
    for secret in (phone, email, address):
        assert secret not in joined


# --- Property 52: artisan validators ----------------------------------------------------------------------------

names = st.one_of(st.text(_ALPHA, min_size=1, max_size=100), st.just(''), st.just('   '),
                  st.integers(101, 160).map(lambda n: 'n' * n))
avails = st.one_of(st.sampled_from(AVAIL), st.sampled_from(['', 'AVAILABLE', 'away', 'on_leave']))
story_in = st.one_of(st.none(), st.text(_ALPHA, max_size=50), st.integers(2001, 2100).map(lambda n: 's' * n))


def _invalid_fields(name, spec, availability, story):
    bad = set()
    if not 1 <= len(name.strip()) <= 100:
        bad.add('name')
    if not 1 <= len(spec.strip()) <= 100:
        bad.add('specialisation')
    if availability not in AVAIL:
        bad.add('availability')
    if story is not None and len(story) > 2000:
        bad.add('story')
    return bad


@hsettings(**settings_hs)
@given(name=names, spec=names, availability=avails, story=story_in)
def test_create_accepts_iff_in_range(env, name, spec, availability, story):
    client, staff, _, _, _ = env
    body = {'name': name, 'specialisation': spec, 'availability': availability}
    if story is not None:
        body['story'] = story
    invalid = _invalid_fields(name, spec, availability, story)
    before = _list_total(client, staff)
    r = client.post('/api/staff/artisans', json=body, headers=staff)
    if not invalid:
        assert r.status_code == 201
        got = client.get(f"/api/staff/artisans/{r.json()['id']}", headers=staff).json()
        assert got['name'] == name.strip() and got['specialisation'] == spec.strip()
        assert got['availability'] == availability and got['story'] == (story or '')
        assert _list_total(client, staff) == before + 1
    else:
        assert r.status_code == 422
        assert invalid <= {d['field'] for d in r.json()['error']['details']}
        assert _list_total(client, staff) == before


@hsettings(**settings_hs)
@given(name=names, spec=names, availability=avails, story=story_in)
def test_update_accepts_iff_in_range(env, name, spec, availability, story):
    client, staff, _, _, _ = env
    created = client.post('/api/staff/artisans', headers=staff, json={
        'name': 'Original', 'specialisation': 'Weaving', 'availability': 'available', 'story': 'orig'})
    aid = created.json()['id']
    original = client.get(f'/api/staff/artisans/{aid}', headers=staff).json()
    body = {'name': name, 'specialisation': spec, 'availability': availability}
    if story is not None:
        body['story'] = story
    invalid = _invalid_fields(name, spec, availability, story)
    r = client.put(f'/api/staff/artisans/{aid}', json=body, headers=staff)
    after = client.get(f'/api/staff/artisans/{aid}', headers=staff).json()
    if not invalid:
        assert r.status_code == 200
        assert after['name'] == name.strip() and after['specialisation'] == spec.strip()
        assert after['availability'] == availability
        assert after['story'] == (story if story is not None else 'orig')
    else:
        assert r.status_code == 422
        assert invalid <= {d['field'] for d in r.json()['error']['details']}
        assert after == original
