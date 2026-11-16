"""Request and response models for the auth module (Req 4.1, 4.4, 4.5, 4.6)."""
from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class RegisterRequest(BaseModel):
    # extra='ignore': a supplied `role` is silently dropped (Req 4.5).
    model_config = ConfigDict(extra='ignore')

    name: Name
    email: Annotated[EmailStr, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=8, max_length=128)]

    @field_validator('password')
    @classmethod
    def _password_rules(cls, v: str) -> str:
        if not any(c.isalpha() for c in v):
            raise ValueError('password must contain at least one letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('password must contain at least one digit')
        return v


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra='ignore')

    email: Annotated[str, Field(max_length=254)]
    password: Annotated[str, Field(max_length=128)]


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str


class LoginOut(BaseModel):
    token: str
    expiresAt: str
    role: str
    user: UserOut


class SessionOut(BaseModel):
    user: UserOut
    role: str
    expiresAt: str
