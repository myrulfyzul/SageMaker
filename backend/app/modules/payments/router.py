"""HTTP layer: GET /api/orders/{id}/payments for the owning customer and for staff."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.errors import NotFound
from app.modules.auth.deps import ConnDep, require_roles
from app.modules.auth.api import SessionInfo
from app.modules.orders import api as orders_api
from app.modules.payments import api
from app.modules.payments.schemas import PaymentOut

router = APIRouter(prefix='/api/orders', tags=['payments'])

OwnerOrStaffDep = Annotated[SessionInfo, Depends(require_roles('customer', 'seller', 'admin'))]


@router.get('/{order_id}/payments', response_model=list[PaymentOut],
            dependencies=[Depends(api.require_demo_mode)])
def list_order_payments(order_id: str, session: OwnerOrStaffDep, conn: ConnDep) -> list[dict[str, Any]]:
    if session.role == 'customer':
        # Foreign and missing orders are indistinguishable (Property 10).
        if orders_api.order_owner_id(conn, order_id) != session.user_id:
            raise NotFound()
    elif not orders_api.order_exists(conn, order_id):
        raise NotFound()
    return api.list_for_order(conn, order_id)
