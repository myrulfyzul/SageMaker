"""Payment request/response schemas. No card, bank or wallet credential field exists (Req 13.8)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

PAYMENT_METHODS = ('card', 'fpx', 'ewallet', 'cod')
PAYMENT_OUTCOMES = ('success', 'failed', 'cancelled', 'pending_cod')

Method = Literal['card', 'fpx', 'ewallet', 'cod']
SimulatedOutcome = Literal['success', 'failed', 'cancelled']


class PaymentRequest(BaseModel):
    """Method and simulated outcome only; any extra field (e.g. a card number) is rejected with 422."""
    model_config = ConfigDict(extra='forbid')

    method: Method
    outcome: SimulatedOutcome | None = None


class PaymentOut(BaseModel):
    id: int
    orderId: str
    method: str
    outcome: str
    amountSen: int
    isDemo: bool
    createdAt: str
