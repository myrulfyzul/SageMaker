"""Request bodies for staff custom-order actions."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class AcceptIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    estimatedPriceSen: StrictInt = Field(ge=1, le=99_999_999, description='Estimated price in integer sen')


class RejectIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(max_length=2000)


class AssignIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    artisanId: StrictInt


class StatusIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: str = Field(max_length=50)
