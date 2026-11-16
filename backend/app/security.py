"""Password hashing and session-token helpers (Req 4.2, 4.6, 5.4)."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# argon2-cffi's PasswordHasher defaults to argon2id.
_hasher = PasswordHasher()

# Hash of a random value, created once per process. Verified against when the email is unknown
# so that unknown-email and wrong-password logins take similar time (design: Login).
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a password. A None hash (unknown email) is checked against a dummy hash and is always False."""
    target = password_hash if password_hash else _DUMMY_HASH
    try:
        ok = _hasher.verify(target, password)
    except (VerificationError, InvalidHashError):
        ok = False
    return ok and password_hash is not None and bool(password_hash)


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_token() -> str:
    """Opaque session token with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 hex digest; only this value is stored."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    """Constant-time comparison of two strings (e.g. stored and presented token hashes)."""
    return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))
