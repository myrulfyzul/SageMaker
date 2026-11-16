"""Payment request/response schemas. No card, bank or wallet credential field exists (Req 13.8)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

PAYMENT_METHODS = ('card', 'fpx', 'ewallet', 'cod')
PAYMENT_OUTCOMES = ('success', 'failed', 'cancelled', 'pending_cod')

Method = Literal['card', 'fpx', 'ewallet', 'cod']
SimulatedOutcome = Literal['success', 'failed', 'cancelled']


# Malaysian providers per method (bank or wallet id as used by the app). Card and COD take none.
FPX_BANKS = frozenset({'maybank2u', 'cimb', 'publicbank', 'rhb', 'hongleong', 'ambank', 'bankislam', 'bsn',
                       'bankrakyat', 'muamalat', 'affin', 'alliance', 'agrobank', 'hsbc', 'ocbc', 'sc', 'uob', 'kfh'})
EWALLETS = frozenset({'tng', 'grabpay', 'boost', 'shopeepay', 'mae', 'duitnow'})
PROVIDERS_BY_METHOD: dict[str, frozenset[str]] = {'fpx': FPX_BANKS, 'ewallet': EWALLETS}


def provider_problem(method: str, provider: Optional[str]) -> Optional[str]:
    """Reason the provider is invalid for the method, or None when it is acceptable (it is optional)."""
    if provider is None:
        return None
    allowed = PROVIDERS_BY_METHOD.get(method)
    if allowed is None:
        return f'no provider is accepted for {method}'
    if provider not in allowed:
        return f'must be one of: {", ".join(sorted(allowed))}'
    return None


# FPX B2C limits in sen (RM 1.00 to RM 30,000.00).
FPX_MIN_SEN = 100
FPX_MAX_SEN = 3_000_000


class PaymentRequest(BaseModel):
    """Method and simulated outcome only; any extra field (e.g. a card number) is rejected with 422."""
    model_config = ConfigDict(extra='forbid')

    method: Method
    outcome: SimulatedOutcome | None = None
    provider: Optional[str] = None


class PaymentOut(BaseModel):
    id: int
    orderId: str
    method: str
    outcome: str
    amountSen: int
    provider: Optional[str] = None
    reference: Optional[str] = None
    isDemo: bool
    createdAt: str
