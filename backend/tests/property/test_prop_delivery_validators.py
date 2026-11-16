"""Property 17: Delivery and field validators (Python side).

**Validates: Requirements 7.2, 7.3, 7.4, 7.5, 12.3, 12.4, 16.1, 16.8**

The checkout delivery validator accepts input iff every field is in range (name 2-100, Malaysian phone, email
well-formed and <= 254, address 10-255, postcode exactly 5 digits, one of the 16 states, notes <= 500), and
otherwise raises a 422 ValidationFailed naming every invalid field. The users profile and address schemas
accept input iff their documented ranges hold.
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from app.errors import ValidationFailed
from app.modules.checkout.schemas import MALAYSIAN_STATES, DeliveryIn, validate_delivery
from app.modules.users.schemas import AddressInput, ProfileUpdate

SETTINGS = settings(max_examples=150, deadline=None)

# Printable text without leading/trailing whitespace ambiguity; stripping is part of the oracle.
TEXT = st.text(alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters=' '), max_size=300)
DIGITS = st.text(alphabet='0123456789', max_size=16)


# ---------------------------------------------------------------- independent oracles
def phone_ok(raw: str) -> bool:
    s = raw.strip().replace(' ', '').replace('-', '')
    for prefix in ('+60', '60', '0'):
        if s.startswith(prefix):
            rest = s[len(prefix):]
            if not (rest.isascii() and rest.isdigit()):
                continue
            if rest[0] == '1' and len(rest) in (9, 10):
                return True
            if rest[0] in '3456789' and len(rest) in (8, 9):
                return True
    return False


def email_ok(raw: str) -> bool:
    s = raw.strip()
    if len(s) > 254 or s.count('@') != 1 or any(c.isspace() for c in s):
        return False
    local, domain = s.split('@')
    return bool(local) and '.' in domain and not domain.startswith('.') and not domain.endswith('.')


def delivery_errors(d: dict) -> set[str]:
    bad = set()
    if not 2 <= len(d['name'].strip()) <= 100:
        bad.add('name')
    if not phone_ok(d['phone']):
        bad.add('phone')
    if not email_ok(d['email']):
        bad.add('email')
    if not 10 <= len(d['address'].strip()) <= 255:
        bad.add('address')
    p = d['postcode'].strip()
    if not (len(p) == 5 and p.isascii() and p.isdigit()):
        bad.add('postcode')
    if d['state'].strip() not in MALAYSIAN_STATES:
        bad.add('state')
    if d['notes'] is not None and len(d['notes'].strip()) > 500:
        bad.add('notes')
    return bad


# ---------------------------------------------------------------- strategies
valid_phone = st.builds(
    lambda prefix, lead, tail, sep: prefix + lead + tail if not sep else prefix + ' ' + lead + '-' + tail,
    st.sampled_from(['+60', '60', '0']),
    st.sampled_from(list('13456789')),
    DIGITS.filter(bool),
    st.booleans(),
)
phone_st = st.one_of(valid_phone, st.builds(lambda p, d: p + d, st.sampled_from(['', '0', '+60', '60']), DIGITS),
                     st.text(max_size=15))

email_st = st.one_of(
    st.builds(lambda a, b, c: f'{a}@{b}.{c}',
              st.text('abcxyz0123._', min_size=1, max_size=20), st.text('abcxyz', min_size=1, max_size=15),
              st.text('abcxyz', min_size=2, max_size=5)),
    st.builds(lambda n: 'a' * (n - len('@b.co')) + '@b.co', st.integers(250, 258)),  # 254/255 boundary
    st.text(max_size=40),
    st.sampled_from(['a@b', '@b.co', 'a b@c.co', 'a@@b.co', 'a@b.', 'plain']),
)
postcode_st = st.one_of(DIGITS, st.text(max_size=7))
state_st = st.one_of(st.sampled_from(MALAYSIAN_STATES), st.sampled_from(MALAYSIAN_STATES).map(str.lower),
                     st.text(max_size=20))
notes_st = st.one_of(st.none(), st.builds(lambda n: 'n' * n, st.integers(495, 505)), TEXT)
name_st = st.one_of(st.builds(lambda n: 'a' * n, st.integers(0, 3)), st.builds(lambda n: 'a' * n, st.integers(98, 102)), TEXT)
address_st = st.one_of(st.builds(lambda n: 'a' * n, st.integers(8, 12)), st.builds(lambda n: 'a' * n, st.integers(253, 257)), TEXT)

delivery_st = st.fixed_dictionaries({
    'name': name_st, 'phone': phone_st, 'email': email_st, 'address': address_st,
    'postcode': postcode_st, 'state': state_st, 'notes': notes_st,
})

GOOD = {'name': 'Aisha Rahman', 'phone': '012-3456789', 'email': 'aisha@example.com',
        'address': '12 Jalan Bukit Bintang', 'postcode': '50200', 'state': 'Kuala Lumpur', 'notes': None}


# ---------------------------------------------------------------- checkout delivery
@SETTINGS
@given(delivery_st)
def test_delivery_accepts_iff_all_fields_valid_and_reports_every_invalid_field(d):
    expected = delivery_errors(d)
    try:
        cleaned = validate_delivery(DeliveryIn(**d))
    except ValidationFailed as exc:
        assert exc.status == 422
        assert {item['field'] for item in exc.details} == {f'delivery.{f}' for f in expected}
        assert expected, 'rejected although every field is valid'
    else:
        assert not expected, f'accepted invalid fields {expected}'
        assert cleaned['name'] == d['name'].strip()
        assert cleaned['postcode'] == d['postcode'].strip()


@SETTINGS
@given(st.sampled_from(sorted(GOOD)), st.one_of(st.none(), st.integers(), st.lists(st.integers(), max_size=2)))
def test_delivery_rejects_non_string_values(field, value):
    d = dict(GOOD)
    d[field] = value
    if field == 'notes' and value is None:
        validate_delivery(DeliveryIn(**d))
        return
    with pytest.raises(ValidationFailed) as ei:
        validate_delivery(DeliveryIn(**d))
    assert f'delivery.{field}' in {i['field'] for i in ei.value.details}


def test_delivery_valid_example_and_boundaries():
    assert validate_delivery(DeliveryIn(**GOOD))['state'] == 'Kuala Lumpur'
    assert len(MALAYSIAN_STATES) == 16
    for state in MALAYSIAN_STATES:
        validate_delivery(DeliveryIn(**{**GOOD, 'state': state}))
    validate_delivery(DeliveryIn(**{**GOOD, 'name': 'ab', 'notes': 'n' * 500, 'address': 'a' * 255}))
    validate_delivery(DeliveryIn(**{**GOOD, 'email': 'a' * 249 + '@b.co'}))  # exactly 254
    with pytest.raises(ValidationFailed):
        validate_delivery(DeliveryIn(**{**GOOD, 'email': 'a' * 250 + '@b.co'}))  # 255


# ---------------------------------------------------------------- users profile and address
def users_name_ok(s: str) -> bool:
    return 1 <= len(s.strip()) <= 100


def users_phone_ok(s: str) -> bool:
    return 8 <= len(s) <= 15 and s.isascii() and s.isdigit()


def accepts(model, **kw) -> bool:
    try:
        model(**kw)
        return True
    except ValidationError:
        return False


users_phone_st = st.one_of(DIGITS, st.text(max_size=16))
users_name_st = st.one_of(st.builds(lambda n: 'a' * n, st.integers(98, 102)), TEXT)


@SETTINGS
@given(users_name_st, users_phone_st)
def test_profile_update_accepts_iff_name_and_phone_in_range(name, phone):
    assert accepts(ProfileUpdate, name=name, phone=phone) == (users_name_ok(name) and users_phone_ok(phone))


@SETTINGS
@given(users_name_st, users_phone_st, postcode_st,
       st.one_of(st.builds(lambda n: 'a' * n, st.integers(198, 202)), TEXT))
def test_address_input_accepts_iff_fields_in_range(name, phone, postcode, line1):
    pc_ok = len(postcode) == 5 and postcode.isascii() and postcode.isdigit()
    expected = (users_name_ok(name) and users_phone_ok(phone) and pc_ok and 1 <= len(line1.strip()) <= 200)
    got = accepts(AddressInput, recipient_name=name, phone=phone, line1=line1, postcode=postcode,
                  city='Ipoh', state='Perak')
    assert got == expected
