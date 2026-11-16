"""Environment-driven settings with strict validation and no fallback secrets."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TOKEN_LIFETIME = 604800
MIN_TOKEN_LIFETIME = 3600
MAX_TOKEN_LIFETIME = 2592000
DEFAULT_TIMEZONE = 'Asia/Kuala_Lumpur'


class ConfigError(Exception):
    """Raised when an environment variable is missing or invalid."""

    def __init__(self, variable: str, reason: str):
        self.variable = variable
        self.reason = reason
        super().__init__(f'Invalid configuration: {variable}: {reason}')


def _parse_origins(raw: str) -> tuple[str, ...]:
    origins = []
    for part in raw.split(','):
        value = part.strip()
        if not value:
            continue
        parsed = urlparse(value)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.path not in ('', '/') or parsed.params or parsed.query or parsed.fragment):
            raise ConfigError('ALLOWED_ORIGINS', f'"{value}" is not an absolute http(s) origin')
        origins.append(value.rstrip('/'))
    return tuple(origins)


def _parse_lifetime(raw: Optional[str]) -> int:
    if raw is None or raw.strip() == '':
        return DEFAULT_TOKEN_LIFETIME
    text = raw.strip()
    if not text.isascii() or not text.isdigit():
        raise ConfigError('TOKEN_LIFETIME_SECONDS', 'must be an integer')
    value = int(text)
    if not MIN_TOKEN_LIFETIME <= value <= MAX_TOKEN_LIFETIME:
        raise ConfigError('TOKEN_LIFETIME_SECONDS', f'must be between {MIN_TOKEN_LIFETIME} and {MAX_TOKEN_LIFETIME}')
    return value


def _parse_media_dir(raw: Optional[str], database_path: Path) -> Path:
    if raw is None or raw.strip() == '':
        return database_path.parent / 'media'
    if '\x00' in raw:
        raise ConfigError('MEDIA_DIR', 'is not a valid path')
    path = Path(raw.strip())
    if path.exists() and not path.is_dir():
        raise ConfigError('MEDIA_DIR', 'exists but is not a directory')
    return path


def _parse_timezone(raw: Optional[str]) -> str:
    name = DEFAULT_TIMEZONE if raw is None or raw.strip() == '' else raw.strip()
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ConfigError('APP_TIMEZONE', f'"{name}" is not a known IANA time zone') from None
    return name


def _parse_stripe_key(raw: Optional[str]) -> str:
    """Sandbox key only: a `sk_live_` key is refused so this prototype can never charge real money."""
    key = (raw or '').strip()
    if not key:
        return ''
    if key.startswith('sk_live_') or key.startswith('rk_live_'):
        raise ConfigError('STRIPE_SECRET_KEY', 'live keys are not accepted; use a sandbox key (sk_test_...)')
    if not (key.startswith('sk_test_') or key.startswith('rk_test_')):
        raise ConfigError('STRIPE_SECRET_KEY', 'must be a Stripe sandbox secret key starting with sk_test_')
    return key


def _parse_public_url(raw: Optional[str]) -> str:
    value = (raw or '').strip().rstrip('/')
    if not value:
        return ''
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.path not in ('', '/'):
        raise ConfigError('PUBLIC_BASE_URL', f'"{value}" is not an absolute http(s) origin')
    return value


@dataclass(frozen=True)
class Settings:
    database_path: Path
    allowed_origins: tuple[str, ...] = ()
    token_lifetime_seconds: int = DEFAULT_TOKEN_LIFETIME
    demo_mode: bool = False
    media_dir: Optional[Path] = None
    app_timezone: str = DEFAULT_TIMEZONE
    # Legacy admin key (optional; empty means the legacy admin endpoint always refuses).
    legacy_admin_key: str = ''
    # Stripe sandbox (empty = simulated prototype gateway). The webhook secret is optional: without it the app
    # confirms payments by asking Stripe directly while it polls.
    stripe_secret_key: str = ''
    stripe_webhook_secret: str = ''
    # Public origin of this API, used for Stripe's return URLs (Render sets RENDER_EXTERNAL_URL itself).
    public_base_url: str = ''

    @property
    def gateway_enabled(self) -> bool:
        return bool(self.stripe_secret_key)

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> 'Settings':
        env = os.environ if environ is None else environ
        raw_db = env.get('DATABASE_PATH') or env.get('SAGEMAKER_DEMO_DB')
        if raw_db is None or raw_db.strip() == '':
            raise ConfigError('DATABASE_PATH', 'is required')
        if '\x00' in raw_db:
            raise ConfigError('DATABASE_PATH', 'is not a valid path')
        database_path = Path(raw_db.strip())
        if database_path.is_dir():
            raise ConfigError('DATABASE_PATH', 'must be a file path, not a directory')
        return cls(
            database_path=database_path,
            allowed_origins=_parse_origins(env.get('ALLOWED_ORIGINS', '')),
            token_lifetime_seconds=_parse_lifetime(env.get('TOKEN_LIFETIME_SECONDS')),
            # Only the exact value "1" enables payments (Req 33.7).
            demo_mode=env.get('DEMO_MODE') == '1',
            media_dir=_parse_media_dir(env.get('MEDIA_DIR'), database_path),
            app_timezone=_parse_timezone(env.get('APP_TIMEZONE')),
            legacy_admin_key=env.get('SAGEMAKER_ADMIN_KEY', ''),
            stripe_secret_key=_parse_stripe_key(env.get('STRIPE_SECRET_KEY')),
            stripe_webhook_secret=(env.get('STRIPE_WEBHOOK_SECRET') or '').strip(),
            public_base_url=_parse_public_url(env.get('PUBLIC_BASE_URL') or env.get('RENDER_EXTERNAL_URL')),
        )
