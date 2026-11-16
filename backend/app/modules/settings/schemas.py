"""Request model for staff settings (Req 6.4)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictInt

MAX_VALUE = 999_999_999


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    defaultLowStockThreshold: StrictInt = Field(ge=0, le=MAX_VALUE)
