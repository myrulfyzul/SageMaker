"""Request and response models for the users module (Req 7.2 to 7.5)."""
from __future__ import annotations

import re
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic.alias_generators import to_camel

PHONE_RE = re.compile(r'^[0-9]{8,15}$')
POSTCODE_RE = re.compile(r'^[0-9]{5}$')

Role = Literal['customer', 'seller', 'admin', 'artisan']

# Surrounding whitespace is trimmed first, so a blank name is rejected as empty.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


def _check_phone(value: str) -> str:
    if not PHONE_RE.fullmatch(value):
        raise ValueError('phone must be 8 to 15 digits')
    return value


class _Model(BaseModel):
    model_config = ConfigDict(extra='forbid', alias_generator=to_camel, populate_by_name=True)


class ProfileUpdate(_Model):
    name: Name
    phone: str

    @field_validator('phone')
    @classmethod
    def _phone(cls, v: str) -> str:
        return _check_phone(v)


class AddressInput(_Model):
    recipient_name: Name
    phone: str
    line1: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    line2: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]] = None
    postcode: str
    city: Name
    state: Name
    is_default: bool = False

    @field_validator('phone')
    @classmethod
    def _phone(cls, v: str) -> str:
        return _check_phone(v)

    @field_validator('postcode')
    @classmethod
    def _postcode(cls, v: str) -> str:
        if not POSTCODE_RE.fullmatch(v):
            raise ValueError('postcode must be exactly 5 digits')
        return v


class FavouritesMerge(_Model):
    product_ids: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=64)]], Field(max_length=500)]


class RoleChange(_Model):
    role: Role


class ProfileOut(BaseModel):
    id: int
    name: str
    email: str
    phone: Optional[str]
    role: str


class AddressOut(BaseModel):
    id: int
    recipientName: str
    phone: str
    line1: str
    line2: Optional[str]
    postcode: str
    city: str
    state: str
    isDefault: bool
