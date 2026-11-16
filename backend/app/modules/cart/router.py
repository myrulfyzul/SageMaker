"""HTTP layer for /api/cart (customer only)."""
from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends

from ..auth.deps import ConnDep, require_customer
from ..auth.api import SessionInfo
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from . import service

router = APIRouter(prefix='/api/cart', tags=['cart'])

CustomerDep = Annotated[SessionInfo, Depends(require_customer)]


class _Model(BaseModel):
    model_config = ConfigDict(extra='ignore', alias_generator=to_camel, populate_by_name=True)


class LineIn(_Model):
    # quantity stays untyped so the service reports a range error (422) for non-integers.
    product_id: str = Field(min_length=1, max_length=64)
    variation_id: Optional[int] = None
    quantity: Any


class MergeIn(_Model):
    lines: Annotated[list[dict[str, Any]], Field(max_length=200)]


@router.get('')
def get_cart(session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return service.view(conn, session.user_id)


@router.post('/lines')
def add_line(body: LineIn, session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return service.add(conn, session.user_id, body.product_id, body.variation_id, body.quantity)


@router.put('/lines')
def set_line(body: LineIn, session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return service.set_quantity(conn, session.user_id, body.product_id, body.variation_id, body.quantity)


@router.delete('/lines/{line_id}')
def delete_line(line_id: int, session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return service.remove(conn, session.user_id, line_id)


@router.post('/merge')
def merge_cart(body: MergeIn, session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return service.merge(conn, session.user_id, body.lines)
