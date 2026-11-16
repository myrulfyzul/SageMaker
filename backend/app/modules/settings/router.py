"""GET/PUT /api/staff/settings (Req 6.4). Staff = seller or admin; others get 403."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app import db
from app.modules.auth.deps import ConnDep, require_staff
from app.modules.auth.api import SessionInfo

from . import api
from .schemas import SettingsIn

router = APIRouter(prefix='/api/staff/settings', tags=['staff-settings'])

StaffDep = Annotated[SessionInfo, Depends(require_staff)]


def _view(conn: Any) -> dict[str, Any]:
    return {'defaultLowStockThreshold': api.get_default_low_stock_threshold(conn)}


@router.get('', summary='Staff-adjustable settings')
def get_settings(session: StaffDep, conn: ConnDep) -> dict[str, Any]:
    return _view(conn)


@router.put('', summary='Update staff-adjustable settings')
def put_settings(body: SettingsIn, session: StaffDep, conn: ConnDep) -> dict[str, Any]:
    with db.transaction(conn):
        api.set_default_low_stock_threshold(conn, body.defaultLowStockThreshold)
    return _view(conn)
