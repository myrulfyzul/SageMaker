"""Request models for production tracking (Req 24.2, 24.3, 24.4, 24.6, 24.7). Invalid fields give HTTP 422."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints
from typing_extensions import Annotated

Priority = Literal['low', 'normal', 'high', 'urgent']
ProductionStatus = Literal['order_confirmed', 'production_assigned', 'in_production', 'quality_checking',
                           'completed', 'ready_for_fulfilment']

Quantity = Annotated[StrictInt, Field(ge=1, le=999999)]
Percent = Annotated[StrictInt, Field(ge=0, le=100)]
Notes = Annotated[str, StringConstraints(max_length=1000)]
ProgressNote = Annotated[str, StringConstraints(max_length=500)]


class JobCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    orderId: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    orderLineId: StrictInt
    quantity: Optional[Quantity] = None  # defaults to the order line quantity


class JobAssign(BaseModel):
    model_config = ConfigDict(extra='forbid')
    artisanId: StrictInt
    quantity: Quantity
    deadline: str  # YYYY-MM-DD, checked in the service so that the error names the `deadline` field
    priority: Priority = 'normal'
    notes: Notes = ''


class StatusChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: ProductionStatus


class ProgressIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    percent: Percent
    note: ProgressNote = ''
