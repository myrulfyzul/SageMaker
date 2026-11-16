"""Staff inventory endpoints (Req 21.1 to 21.7). Staff = seller or admin; others get 403."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.modules.auth.deps import ConnDep, require_staff
from app.modules.auth.api import SessionInfo

from . import service
from .schemas import AdjustmentIn, ThresholdIn

router = APIRouter(prefix='/api/staff/inventory', tags=['staff-inventory'])

StaffDep = Annotated[SessionInfo, Depends(require_staff)]


@router.get('', summary='Stock of every product with low-stock flags')
def list_inventory(session: StaffDep, conn: ConnDep,
                   low_only: Annotated[bool, Query(description='Only products at or below their threshold')] = False,
                   ) -> dict[str, Any]:
    return service.list_inventory(conn, low_only)


@router.get('/{product_id}', summary='Stock, threshold and low-stock flag of one product')
def get_inventory(product_id: str, session: StaffDep, conn: ConnDep) -> dict[str, Any]:
    return service.get_inventory(conn, product_id)


@router.post('/{product_id}/adjustments', status_code=201, summary='Adjust stock')
def create_adjustment(product_id: str, body: AdjustmentIn, session: StaffDep, conn: ConnDep) -> dict[str, Any]:
    return service.adjust(conn, product_id, body.variationId, body.delta, body.reason, session.user_id)


@router.get('/{product_id}/adjustments', summary='Adjustment history, newest first')
def list_adjustments(product_id: str, session: StaffDep, conn: ConnDep) -> dict[str, Any]:
    return {'items': service.history(conn, product_id)}


@router.put('/{product_id}/threshold', summary='Set the low-stock threshold')
def set_threshold(product_id: str, body: ThresholdIn, session: StaffDep, conn: ConnDep) -> dict[str, Any]:
    return service.set_threshold(conn, product_id, body.lowStockThreshold)
