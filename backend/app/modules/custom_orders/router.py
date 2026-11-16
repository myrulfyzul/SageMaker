"""Custom-order endpoints: customer (Req 16), reference-image media and staff management (Req 25)."""
from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from app.errors import ValidationFailed
from app.modules.auth.deps import ConnDep, SessionDep, require_customer, require_staff
from app.modules.auth.api import SessionInfo
from app.pagination import PageDep

from . import service
from .schemas import AcceptIn, AssignIn, RejectIn, StatusIn

router = APIRouter(prefix='/api/custom-orders', tags=['custom-orders'])
media_router = APIRouter(prefix='/api/media', tags=['custom-orders'])
staff_router = APIRouter(prefix='/api/staff/custom-orders', tags=['staff-custom-orders'],
                         dependencies=[Depends(require_staff)])

CustomerUser = Annotated[SessionInfo, Depends(require_customer)]


@router.get('', summary='List my custom orders, newest first')
def list_own(session: CustomerUser, conn: ConnDep, page: PageDep) -> dict[str, Any]:
    return service.list_own(conn, session.user_id, page.limit, page.offset)


@router.post('', status_code=201, summary='Submit a custom order (multipart, up to 5 reference images)')
def create(request: Request, session: CustomerUser, conn: ConnDep,
           product_type: Annotated[Optional[str], Form(alias='productType')] = None,
           description: Annotated[Optional[str], Form()] = None,
           quantity: Annotated[Optional[str], Form()] = None,
           preferred_date: Annotated[Optional[str], Form(alias='preferredDate')] = None,
           images: Annotated[Optional[list[UploadFile]], File()] = None) -> dict[str, Any]:
    settings = request.app.state.settings
    files = [(f.filename or '', f.file) for f in (images or []) if f.filename or f.size]
    return service.create(conn, session.user_id, product_type=product_type, description=description,
                          quantity=quantity, preferred_date=preferred_date, files=files,
                          media_dir=settings.media_dir, tz=settings.app_timezone)


@router.get('/{custom_order_id}', summary='My custom order detail')
def get_own(custom_order_id: int, session: CustomerUser, conn: ConnDep) -> dict[str, Any]:
    return service.get_own(conn, session.user_id, custom_order_id)


@media_router.get('/{filename}', summary='Custom-order reference image (owner or staff)')
def get_media(filename: str, request: Request, session: SessionDep, conn: ConnDep) -> FileResponse:
    path, content_type = service.media_file(conn, filename, session.user_id, session.role,
                                            request.app.state.settings.media_dir)
    return FileResponse(path, media_type=content_type, headers={'Cache-Control': 'private, max-age=3600'})


@staff_router.get('', summary='List custom orders, newest first, optional status filter')
def list_staff(conn: ConnDep, page: PageDep, status: Optional[str] = None) -> dict[str, Any]:
    return service.list_staff(conn, status or None, page.limit, page.offset)


@staff_router.get('/{custom_order_id}', summary='Custom order detail (staff)')
def get_staff(custom_order_id: int, conn: ConnDep) -> dict[str, Any]:
    return service.get_staff(conn, custom_order_id)


@staff_router.post('/{custom_order_id}/accept', summary='Accept a submitted request with an estimated price')
def accept(custom_order_id: int, body: AcceptIn, conn: ConnDep) -> dict[str, Any]:
    return service.accept(conn, custom_order_id, body.estimatedPriceSen)


@staff_router.post('/{custom_order_id}/reject', summary='Reject a submitted request with a reason')
def reject(custom_order_id: int, body: RejectIn, conn: ConnDep) -> dict[str, Any]:
    reason = body.reason.strip()
    if not 5 <= len(reason) <= 500:
        raise ValidationFailed([{'field': 'reason', 'reason': 'must be 5 to 500 characters'}])
    return service.reject(conn, custom_order_id, reason)


@staff_router.post('/{custom_order_id}/assign-artisan', summary='Assign an active artisan and create a production job')
def assign_artisan(custom_order_id: int, body: AssignIn, conn: ConnDep) -> dict[str, Any]:
    return service.assign_artisan(conn, custom_order_id, body.artisanId)


@staff_router.post('/{custom_order_id}/status', summary='Move to in_progress or completed')
def change_status(custom_order_id: int, body: StatusIn, conn: ConnDep) -> dict[str, Any]:
    return service.change_status(conn, custom_order_id, body.status)
