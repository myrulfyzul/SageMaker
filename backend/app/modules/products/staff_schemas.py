"""Request models for staff product management (Req 20.1, 20.2, 20.7).

Integers are strict (no strings, floats or booleans). Pydantic reports each invalid field, which the global handler
turns into HTTP 422 with one detail per field."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints
from typing_extensions import Annotated

MAX_PRICE_SEN = 99_999_999
MAX_STOCK = 999_999

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(max_length=2000)]


class VariationIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: Optional[StrictInt] = Field(default=None, description='Existing variation id (updates only)')
    label: Label
    priceDeltaSen: StrictInt = Field(default=0, ge=-MAX_PRICE_SEN, le=MAX_PRICE_SEN)
    stock: Optional[StrictInt] = Field(default=None, ge=0, le=MAX_STOCK,
                                       description='Opening stock of a new variation; not allowed for existing ones')
    isActive: StrictBool = True


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Name
    description: Description = ''
    categoryId: StrictInt
    priceSen: StrictInt = Field(ge=1, le=MAX_PRICE_SEN)
    stock: StrictInt = Field(default=0, ge=0, le=MAX_STOCK)
    lowStockThreshold: Optional[StrictInt] = Field(default=None, ge=0, le=MAX_STOCK)
    madeToOrder: StrictBool = False
    artisanId: Optional[StrictInt] = None
    variations: list[VariationIn] = Field(default_factory=list, max_length=20)


class ProductUpdate(BaseModel):
    """Omitted optional fields keep their value; `artisanId: null` removes the artisan link;
    `variations` (when present) lists the variations to keep, others are deactivated."""
    model_config = ConfigDict(extra='forbid')
    name: Name
    description: Optional[Description] = None
    categoryId: StrictInt
    priceSen: StrictInt = Field(ge=1, le=MAX_PRICE_SEN)
    lowStockThreshold: Optional[StrictInt] = Field(default=None, ge=0, le=MAX_STOCK)
    madeToOrder: Optional[StrictBool] = None
    artisanId: Optional[StrictInt] = None
    variations: Optional[list[VariationIn]] = Field(default=None, max_length=20)


class ActiveUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    isActive: StrictBool
