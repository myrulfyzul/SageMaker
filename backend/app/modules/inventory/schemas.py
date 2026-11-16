"""Request models for staff inventory endpoints. Strict integers; each invalid field is reported (Req 21.4, 21.6)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt

MAX_VALUE = 999_999_999


class AdjustmentIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    delta: StrictInt = Field(ge=-MAX_VALUE, le=MAX_VALUE)
    reason: str = Field(min_length=1, max_length=255)
    variationId: Optional[StrictInt] = None


class ThresholdIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lowStockThreshold: StrictInt = Field(ge=0, le=MAX_VALUE)
