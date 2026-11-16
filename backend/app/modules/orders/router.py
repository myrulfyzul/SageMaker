"""HTTP layer: customer orders and payment retry (/api/orders), staff orders (/api/staff/orders)."""
from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query, Request

from app.modules.auth.deps import ConnDep, require_customer, require_staff
from app.modules.auth.api import SessionInfo
from app.modules.orders import service
from app.modules.orders.schemas import StatusChange
from app.modules.payments import api as payments_api
from app.pagination import PageDep

router = APIRouter(prefix='/api/orders', tags=['orders'])
staff_router = APIRouter(prefix='/api/staff/orders', tags=['staff-orders'])

CustomerDep = Annotated[SessionInfo, Depends(require_customer)]
StaffDep = Annotated[SessionInfo, Depends(require_staff)]


@router.get('', summary='My orders, newest first')
def list_my_orders(
    session: CustomerDep, conn: ConnDep,
    limit: Annotated[int, Query(ge=1, le=50, description='Page size, 1 to 50')] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return service.list_for_customer(conn, session.user_id, limit, offset)


@router.get('/{order_id}', summary='One of my orders with its timeline')
def get_my_order(order_id: str, session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return service.customer_detail(conn, session.user_id, order_id)


@router.post('/{order_id}/payments', dependencies=[Depends(payments_api.require_demo_mode)],
             summary='Retry a failed payment (simulated)')
def retry_payment(order_id: str, body: payments_api.PaymentRequest, request: Request, session: CustomerDep,
                  conn: ConnDep) -> dict[str, Any]:
    payments_api.reject_simulated_when_gateway(request.app.state.settings, body.method)
    return service.retry_payment(conn, session.user_id, order_id, body)


@staff_router.get('', summary='All orders with status filter and search')
def list_staff_orders(
    session: StaffDep, conn: ConnDep, page: PageDep,
    status: Annotated[Optional[str], Query(description='Fulfilment status filter')] = None,
    q: Annotated[Optional[str], Query(min_length=1, max_length=100, description='Order id or customer name')] = None,
) -> dict[str, Any]:
    return service.list_for_staff(conn, status, q, page.limit, page.offset)


@staff_router.get('/{order_id}', summary='Order detail for staff')
def get_staff_order(order_id: str, session: StaffDep, conn: ConnDep) -> dict[str, Any]:
    return service.staff_detail(conn, order_id)


@staff_router.post('/{order_id}/status', summary='Change fulfilment status')
def change_order_status(order_id: str, body: StatusChange, session: StaffDep, conn: ConnDep) -> dict[str, Any]:
    return service.change_status(conn, order_id, body, session.user_id)
