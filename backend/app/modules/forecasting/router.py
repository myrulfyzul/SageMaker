"""Staff forecast endpoint (Req 27)."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from app.modules.auth.deps import ConnDep, require_staff
from app.modules.auth.api import SessionInfo

from . import service

router = APIRouter(prefix='/api/staff/forecast', tags=['forecasting'])

StaffUser = Annotated[SessionInfo, Depends(require_staff)]


@router.get('/{product_id}', summary='Three-month demand forecast for a product (staff)')
def get_forecast(product_id: str, request: Request, _: StaffUser, conn: ConnDep) -> dict[str, Any]:
    return service.forecast(conn, product_id, request.app.state.settings.app_timezone)
