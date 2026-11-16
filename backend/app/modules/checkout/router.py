"""HTTP layer: POST /api/checkout (customer only; 503 unless DEMO_MODE=1)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.modules.auth.deps import ConnDep, require_customer
from app.modules.auth.api import SessionInfo
from app.modules.payments import api as payments_api

from . import service
from .schemas import CheckoutIn

router = APIRouter(prefix='/api', tags=['checkout'])

CustomerDep = Annotated[SessionInfo, Depends(require_customer)]


@router.post('/checkout', status_code=201, dependencies=[Depends(payments_api.require_demo_mode)],
             summary='Place an order from the cart (simulated payment)')
def checkout(body: CheckoutIn, session: CustomerDep, conn: ConnDep) -> JSONResponse:
    order, created = service.place_order(conn, session.user_id, body)
    return JSONResponse(order, status_code=201 if created else 200)
