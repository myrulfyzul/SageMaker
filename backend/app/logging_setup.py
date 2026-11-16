"""Logging configuration with a filter that redacts sensitive values."""
from __future__ import annotations

import logging
import re

SENSITIVE_KEYS = ('password_hash', 'token_hash', 'password', 'token', 'phone', 'email', 'address',
                  'private_phone', 'private_email', 'private_address')
REDACTED = '[REDACTED]'

# key=value, key: value, 'key': 'value', "key": "value"
_KEYS = '|'.join(sorted(SENSITIVE_KEYS, key=len, reverse=True))
_PATTERN = re.compile(
    r'''(?P<key>["']?\b(?:%s)\b["']?\s*[:=]\s*)(?P<val>"[^"]*"|'[^']*'|[^\s,;}\]]+)''' % _KEYS,
    re.IGNORECASE,
)
_BEARER = re.compile(r'(Bearer\s+)[A-Za-z0-9._~+/=-]+', re.IGNORECASE)


def redact(text: str) -> str:
    text = _PATTERN.sub(lambda m: m.group('key') + REDACTED, text)
    return _BEARER.sub(lambda m: m.group(1) + REDACTED, text)


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        record.msg = redact(message)
        record.args = None
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


_factory_installed = False


def _install_record_factory() -> None:
    """Redact at record creation so every logger, level and handler is covered."""
    global _factory_installed
    if _factory_installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        record.msg = redact(message)
        record.args = None
        return record

    logging.setLogRecordFactory(factory)
    _factory_installed = True


def configure_logging(level: int = logging.INFO) -> None:
    _install_record_factory()
    root = logging.getLogger()
    if not any(isinstance(f, RedactionFilter) for f in root.filters):
        root.addFilter(RedactionFilter())
    if not root.handlers:
        logging.basicConfig(level=level, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    root.setLevel(level)
    # Filters on the root logger do not apply to records from child loggers, so attach to handlers too.
    for handler in root.handlers:
        if not any(isinstance(f, RedactionFilter) for f in handler.filters):
            handler.addFilter(RedactionFilter())
