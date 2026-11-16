"""Input models and status constants for the orders module."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

LEGACY_PACKING = 'packing'
PREPARING = 'preparing'

# Req 14.6 / Req 22.13: a stored legacy 'packing' is read as 'preparing' and never written.
STATUS_ALIASES = {LEGACY_PACKING: PREPARING}

# Orders in these fulfilment states never count as revenue or sales (Req 19.6).
NON_REVENUE_STATUSES = ('cancelled', 'payment_failed')
# Payment statuses that count as revenue (design O2).
REVENUE_PAYMENT_STATUSES = ('paid', 'pending_cod', 'demo_simulated_not_charged')


def normalise_status(status: str) -> str:
    return STATUS_ALIASES.get(status, status)


class StatusChange(BaseModel):
    """Staff status change body; length rules are checked after the transition so a bad transition is 409."""
    model_config = ConfigDict(extra='forbid')

    status: Literal['placed', 'confirmed', 'preparing', 'shipped', 'delivered', 'cancelled', 'payment_failed']
    shipping_reference: Optional[str] = None
    reason: Optional[str] = None


class NewOrderLine(BaseModel):
    model_config = ConfigDict(extra='forbid')

    product_id: str
    variation_id: Optional[int] = None
    sku_key: str
    name: str
    variation_label: Optional[str] = None
    unit_price_sen: int = Field(gt=0)
    quantity: int = Field(ge=1, le=20)


class NewOrder(BaseModel):
    """Everything needed to insert an order; prices are already server-computed by the caller."""
    model_config = ConfigDict(extra='forbid')

    user_id: int
    idempotency_key: str
    customer_name: str
    email: str
    phone: str
    delivery_address: str
    delivery_postcode: Optional[str] = None
    delivery_state: Optional[str] = None
    delivery_notes: Optional[str] = None
    payment_method: str
    payment_status: str
    status: str = 'placed'
    shipping_fee_sen: int = Field(ge=0)
    lines: list[NewOrderLine] = Field(min_length=1)
    source: str = 'app'
    is_demo: int = 1
    created_at: Optional[str] = None
