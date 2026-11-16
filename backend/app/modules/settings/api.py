"""Public interface of the settings module (Req 6.4): staff-adjustable values stored in `app_settings`."""
from __future__ import annotations

import sqlite3

from app.errors import ValidationFailed
from app.time_utils import utc_now_iso

MAX_THRESHOLD = 999_999_999
DEFAULT_LOW_STOCK_THRESHOLD = 5
_KEY = 'default_low_stock_threshold'


def get_default_low_stock_threshold(conn: sqlite3.Connection) -> int:
    """Default threshold for new products; 5 when never set or the stored value is unusable."""
    row = conn.execute('SELECT value FROM app_settings WHERE key = ?', (_KEY,)).fetchone()
    if row is None:
        return DEFAULT_LOW_STOCK_THRESHOLD
    try:
        value = int(row['value'])
    except (TypeError, ValueError):
        return DEFAULT_LOW_STOCK_THRESHOLD
    return value if 0 <= value <= MAX_THRESHOLD else DEFAULT_LOW_STOCK_THRESHOLD


def set_default_low_stock_threshold(conn: sqlite3.Connection, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_THRESHOLD:
        raise ValidationFailed([{'field': 'defaultLowStockThreshold',
                                 'reason': f'must be a whole number from 0 to {MAX_THRESHOLD}'}])
    conn.execute(
        'INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) '
        'ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at',
        (_KEY, str(value), utc_now_iso()))
