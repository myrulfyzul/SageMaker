"""Money_Sen helpers. All amounts are integers in sen (1 RM = 100 sen); no floats."""
from __future__ import annotations

MAX_SEN = 99_999_999


def is_sen(value: object) -> bool:
    """True for a real int (bool and float are rejected)."""
    return isinstance(value, int) and not isinstance(value, bool)


def require_sen(value: object, *, minimum: int = 0, maximum: int = MAX_SEN) -> int:
    if not is_sen(value):
        raise ValueError('amount must be an integer number of sen')
    if not minimum <= value <= maximum:  # type: ignore[operator]
        raise ValueError(f'amount must be between {minimum} and {maximum} sen')
    return value  # type: ignore[return-value]


def line_total(unit_price_sen: int, quantity: int) -> int:
    return unit_price_sen * quantity


def div_round_half_up(numerator: int, denominator: int) -> int:
    """Integer division rounding half up for non-negative numerator and positive denominator."""
    if denominator <= 0 or numerator < 0:
        raise ValueError('denominator must be positive and numerator non-negative')
    return (numerator * 2 + denominator) // (2 * denominator)


def format_rm(sen: int) -> str:
    """Same output as the Flutter money(): 'RM 12.34'."""
    sign = '-' if sen < 0 else ''
    whole, cents = divmod(abs(sen), 100)
    return f'RM {sign}{whole}.{cents:02d}'
