"""Request model and delivery validators for POST /api/checkout (Req 12.3, 12.4, 12.6)."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.errors import ValidationFailed
from app.modules.payments.api import Method, SimulatedOutcome

MALAYSIAN_STATES = (
    'Johor', 'Kedah', 'Kelantan', 'Melaka', 'Negeri Sembilan', 'Pahang', 'Perak', 'Perlis', 'Pulau Pinang',
    'Sabah', 'Sarawak', 'Selangor', 'Terengganu', 'Kuala Lumpur', 'Labuan', 'Putrajaya',
)
POSTCODE_RE = re.compile(r'^[0-9]{5}$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
# Mobile (01x) and landline (03-09) numbers, with optional +60 / 60 / 0 prefix; spaces and dashes ignored.
MY_PHONE_RE = re.compile(r'^(?:\+?60|0)(?:1[0-9]{8,9}|[3-9][0-9]{7,8})$')
IDEMPOTENCY_MIN, IDEMPOTENCY_MAX = 10, 80
NOTES_MAX = 500


class _Model(BaseModel):
    model_config = ConfigDict(extra='forbid', alias_generator=to_camel, populate_by_name=True)


class DeliveryIn(_Model):
    # Loosely typed on purpose: `validate_delivery` reports every invalid field together (422).
    name: Any = None
    phone: Any = None
    email: Any = None
    address: Any = None
    postcode: Any = None
    state: Any = None
    notes: Any = None


class CheckoutIn(_Model):
    idempotency_key: Any = None
    delivery: DeliveryIn
    method: Method
    outcome: Optional[SimulatedOutcome] = None


def _text(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) else None


def validate_delivery(d: DeliveryIn) -> dict[str, Optional[str]]:
    """Return cleaned delivery fields or raise ValidationFailed naming each invalid field."""
    problems: list[dict[str, str]] = []

    def bad(field: str, reason: str) -> None:
        problems.append({'field': f'delivery.{field}', 'reason': reason})

    name, phone, email = _text(d.name), _text(d.phone), _text(d.email)
    address, postcode, state = _text(d.address), _text(d.postcode), _text(d.state)
    if name is None or not 2 <= len(name) <= 100:
        bad('name', 'must be 2 to 100 characters')
    if phone is None or not MY_PHONE_RE.fullmatch(re.sub(r'[\s-]', '', phone)):
        bad('phone', 'must be a valid Malaysian phone number')
    if email is None or len(email) > 254 or not EMAIL_RE.fullmatch(email):
        bad('email', 'must be a valid email address of at most 254 characters')
    if address is None or not 10 <= len(address) <= 255:
        bad('address', 'must be 10 to 255 characters')
    if postcode is None or not POSTCODE_RE.fullmatch(postcode):
        bad('postcode', 'must be exactly 5 digits')
    if state is None or state not in MALAYSIAN_STATES:
        bad('state', 'must be one of the 16 Malaysian states and federal territories')
    notes: Optional[str] = None
    if d.notes is not None:
        if not isinstance(d.notes, str) or len(d.notes.strip()) > NOTES_MAX:
            bad('notes', f'must be at most {NOTES_MAX} characters')
        else:
            notes = d.notes.strip() or None
    if problems:
        raise ValidationFailed(problems, message='Delivery details are invalid')
    return {'name': name, 'phone': phone, 'email': email, 'address': address, 'postcode': postcode,
            'state': state, 'notes': notes}


def validate_idempotency_key(key: Any) -> str:
    if not isinstance(key, str) or not IDEMPOTENCY_MIN <= len(key) <= IDEMPOTENCY_MAX:
        raise ValidationFailed(
            [{'field': 'idempotencyKey',
              'reason': f'must be {IDEMPOTENCY_MIN} to {IDEMPOTENCY_MAX} characters'}],
            message='Idempotency key is invalid')
    return key


Outcome = Literal['success', 'failed', 'cancelled']
