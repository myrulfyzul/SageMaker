"""Staff analytics endpoints (Req 19.2, 19.3, 26)."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from app.modules.auth.deps import ConnDep, require_staff
from app.modules.auth.api import SessionInfo

from . import service

router = APIRouter(prefix='/api/staff/analytics', tags=['analytics'])

StaffUser = Annotated[SessionInfo, Depends(require_staff)]


@router.get('/dashboard', summary='Dashboard KPIs and chart series (staff)')
def dashboard(request: Request, _: StaffUser, conn: ConnDep) -> dict[str, Any]:
    return service.dashboard(conn, request.app.state.settings.app_timezone)


@router.get('/sales', summary='Sales analytics for a date range, max 24 months (staff)')
def sales(request: Request, _: StaffUser, conn: ConnDep, start: date, end: date) -> dict[str, Any]:
    return service.sales(conn, start, end, request.app.state.settings.app_timezone)
