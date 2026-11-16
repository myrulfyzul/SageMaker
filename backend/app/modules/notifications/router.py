"""HTTP layer: /api/notifications for customers, sellers and admins (Artisan_User gets 403). In-app only."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.errors import NotFound
from app.modules.auth.deps import ConnDep, require_roles
from app.modules.auth.api import SessionInfo
from app.modules.notifications import api
from app.pagination import PageDep

router = APIRouter(prefix='/api/notifications', tags=['notifications'])

NotifUserDep = Annotated[SessionInfo, Depends(require_roles('customer', 'seller', 'admin'))]


@router.get('', summary='My notifications, newest first, with unread count')
def list_notifications(session: NotifUserDep, conn: ConnDep, page: PageDep) -> dict[str, Any]:
    return api.list_for_user(conn, session.user_id, page.limit, page.offset)


# Declared before '/{id}/read' so 'read-all' is never parsed as an id.
@router.post('/read-all', summary='Mark all my notifications as read')
def read_all(session: NotifUserDep, conn: ConnDep) -> dict[str, Any]:
    return api.mark_all_read(conn, session.user_id)


@router.post('/{notification_id}/read', summary='Mark one of my notifications as read')
def read_one(notification_id: str, session: NotifUserDep, conn: ConnDep) -> dict[str, Any]:
    # A non-numeric id is treated like a missing one so every unknown id yields the same 404.
    if not notification_id.isascii() or not notification_id.isdigit() or len(notification_id) > 18:
        raise NotFound()
    return api.mark_read(conn, session.user_id, int(notification_id))
