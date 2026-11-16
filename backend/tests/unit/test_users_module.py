"""Users module core: validators, customer creation, profile, address CRUD and default handling."""
from __future__ import annotations

import pytest
from hypothesis import given, settings as hsettings, strategies as st
from pydantic import ValidationError

from app import db
from app.errors import Conflict, NotFound
from app.migrations.runner import run_migrations
from app.modules.users import api as users_api
from app.modules.users import service
from app.modules.users.schemas import AddressInput, ProfileUpdate


HASH_A = 'hash-' + 'a'
HASH_B = 'hash-' + 'b'


@pytest.fixture()
def conn(tmp_path):
    path = tmp_path / 'users.sqlite3'
    run_migrations(path)
    c = db.connect(path)
    yield c
    c.close()


def _addr(**over):
    base = dict(recipientName='Aisha', phone='0123456789', line1='1 Jalan Satu', postcode='50000',
                city='Kuala Lumpur', state='Wilayah Persekutuan')
    base.update(over)
    return AddressInput(**base)


def _customer(conn, email='a@example.com'):
    with db.transaction(conn):
        return users_api.create_customer(conn, name='Aisha', email=email, password_hash=HASH_A)


def test_create_customer_and_lookup_case_insensitive(conn):
    user = _customer(conn, 'Aisha@Example.com')
    assert user['role'] == 'customer' and 'passwordHash' not in user
    found = users_api.find_by_email(conn, 'AISHA@example.COM')
    assert found and found['id'] == user['id'] and 'passwordHash' not in found
    assert users_api.get_auth_record(conn, 'aisha@example.com')['passwordHash'] == HASH_A
    assert users_api.find_by_email(conn, 'nobody@example.com') is None


def test_duplicate_email_conflict_creates_nothing(conn):
    _customer(conn, 'dup@example.com')
    with pytest.raises(Conflict):
        with db.transaction(conn):
            users_api.create_customer(conn, name='B', email='DUP@example.com', password_hash=HASH_B)
    assert conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1


def test_profile_update_and_validation(conn):
    user = _customer(conn)
    out = service.update_profile(conn, user['id'], ProfileUpdate(name=' New Name ', phone='01234567'))
    assert out['name'] == 'New Name' and out['phone'] == '01234567'
    for bad in [dict(name='', phone='01234567'), dict(name='x' * 101, phone='01234567'),
                dict(name='ok', phone='1234567'), dict(name='ok', phone='1' * 16), dict(name='ok', phone='12345abc9')]:
        with pytest.raises(ValidationError):
            ProfileUpdate(**bad)
    assert service.get_user(conn, user['id'])['name'] == 'New Name'


def test_address_validation():
    for over in [dict(postcode='5000'), dict(postcode='500000'), dict(postcode='5000a'), dict(recipientName=''),
                 dict(line1='x' * 201), dict(line2='x' * 201), dict(city='x' * 101), dict(phone='123'), dict(state='')]:
        with pytest.raises(ValidationError):
            _addr(**over)
    assert _addr(line2='').line2 == ''
    with pytest.raises(ValidationError):
        AddressInput(**{**_addr().model_dump(), 'unknown': 1})


def test_address_crud_and_single_default(conn):
    uid = _customer(conn)['id']
    a = service.create_address(conn, uid, _addr(isDefault=True))
    b = service.create_address(conn, uid, _addr(line1='2 Jalan Dua', isDefault=True))
    defaults = [x['id'] for x in service.list_addresses(conn, uid) if x['isDefault']]
    assert defaults == [b['id']]
    assert service.set_default_address(conn, uid, a['id'])['isDefault'] is True
    assert [x['id'] for x in service.list_addresses(conn, uid) if x['isDefault']] == [a['id']]
    upd = service.update_address(conn, uid, b['id'], _addr(line1='Changed', isDefault=True))
    assert upd['line1'] == 'Changed' and upd['isDefault'] is True
    assert [x['id'] for x in service.list_addresses(conn, uid) if x['isDefault']] == [b['id']]
    service.delete_address(conn, uid, a['id'])
    assert [x['id'] for x in service.list_addresses(conn, uid)] == [b['id']]


def test_foreign_and_missing_addresses_give_identical_404(conn):
    owner = _customer(conn, 'o@example.com')['id']
    other = _customer(conn, 'p@example.com')['id']
    addr = service.create_address(conn, owner, _addr())
    errors = []
    for fn in (lambda: service.update_address(conn, other, addr['id'], _addr()),
               lambda: service.set_default_address(conn, other, addr['id']),
               lambda: service.delete_address(conn, other, addr['id']),
               lambda: service.delete_address(conn, other, 9999)):
        with pytest.raises(NotFound) as ei:
            fn()
        errors.append((ei.value.status, ei.value.code, ei.value.message))
    assert len(set(errors)) == 1
    assert service.list_addresses(conn, owner)[0]['line1'] == '1 Jalan Satu'


def test_role_change_deactivate_and_favourites(conn):
    uid = _customer(conn)['id']
    assert service.change_role(conn, uid, 'seller')['role'] == 'seller'
    with pytest.raises(ValueError):
        service.change_role(conn, uid, 'root')
    with pytest.raises(NotFound):
        service.change_role(conn, 9999, 'admin')
    service.deactivate_user(conn, uid)
    assert users_api.find_by_email(conn, 'a@example.com')['isActive'] is False
    with pytest.raises(NotFound):
        service.deactivate_user(conn, 9999)
    assert users_api.favourite_product_ids(conn, uid) == []


@hsettings(max_examples=25, deadline=None)
@given(st.lists(st.integers(min_value=0, max_value=3), min_size=1, max_size=8))
def test_at_most_one_default_after_any_default_changes(tmp_path_factory, picks):
    """Req 7.6: after any sequence of default changes, exactly one address is default."""
    path = tmp_path_factory.mktemp('prop') / 'u.sqlite3'
    run_migrations(path)
    c = db.connect(path)
    try:
        uid = _customer(c)['id']
        ids = [service.create_address(c, uid, _addr(line1=f'L{i}'))['id'] for i in range(4)]
        for p in picks:
            service.set_default_address(c, uid, ids[p])
            assert sum(1 for x in service.list_addresses(c, uid) if x['isDefault']) == 1
    finally:
        c.close()
