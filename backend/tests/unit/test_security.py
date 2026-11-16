import logging
import secrets

from app import security
from app.logging_setup import configure_logging


def test_hash_and_verify():
    pw = secrets.token_urlsafe(12)
    h = security.hash_password(pw)
    assert h.startswith('$argon2id$') and pw not in h
    assert security.verify_password(pw, h)
    assert not security.verify_password(pw + 'x', h)


def test_unknown_email_uses_dummy_and_fails():
    assert security.verify_password('anything', None) is False
    assert security.verify_password('anything', '') is False
    assert security.verify_password('anything', 'not-a-hash') is False


def test_tokens():
    t = security.new_token()
    assert len(t) >= 43 and t != security.new_token()
    h = security.hash_token(t)
    assert len(h) == 64 and t not in h
    assert security.tokens_equal(h, security.hash_token(t))
    assert not security.tokens_equal(h, security.hash_token(t + 'x'))


def test_redaction_all_levels(caplog):
    configure_logging()
    secret = secrets.token_hex(8)
    caplog.set_level(logging.DEBUG)
    log = logging.getLogger('app.artisans')
    for fn in (log.debug, log.info, log.warning, log.error, log.critical):
        fn('artisan phone=%s email: %s password_hash=%s token_hash=%s', secret, secret, secret, secret)
    assert caplog.records
    assert secret not in caplog.text
