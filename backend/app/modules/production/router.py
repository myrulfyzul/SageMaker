"""Production endpoints (Req 6.7, 6.8, 24). Staff may use all of them; an Artisan_User may only view and update
progress of jobs assigned to their own profile, and every other endpoint answers 403."""
from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query, Request

from app.modules.auth.deps import ConnDep, require_roles, require_staff
from app.modules.auth.api import SessionInfo
from app.pagination import PageDep

from . import service
from .schemas import JobAssign, JobCreate, ProgressIn, StatusChange

router = APIRouter(prefix='/api/production', tags=['production'])

ProductionUser = Annotated[SessionInfo, Depends(require_roles('seller', 'admin', 'artisan'))]
StaffUser = Annotated[SessionInfo, Depends(require_staff)]


def _tz(request: Request) -> str:
    return request.app.state.settings.app_timezone


@router.get('/jobs', summary='List production jobs (filters AND-combined; view=list|board)')
def list_jobs(request: Request, session: ProductionUser, conn: ConnDep, page: PageDep,
              status: Optional[str] = None, artisan_id: Optional[int] = None, priority: Optional[str] = None,
              view: Annotated[str, Query(description='list or board')] = 'list') -> dict[str, Any]:
    return service.list_jobs(conn, tz=_tz(request), status=status, artisan_id=artisan_id, priority=priority,
                             view=view, limit=page.limit, offset=page.offset,
                             artisan_user_id=session.user_id if session.role == 'artisan' else None)


@router.post('/jobs', status_code=201, summary='Create a job for an order line (staff)')
def create_job(body: JobCreate, request: Request, _: StaffUser, conn: ConnDep) -> dict[str, Any]:
    return service.create_manual(conn, body, _tz(request))


@router.get('/jobs/{job_id}', summary='Job detail with progress history')
def get_job(job_id: int, request: Request, session: ProductionUser, conn: ConnDep) -> dict[str, Any]:
    if session.role == 'artisan':
        service.assert_job_assigned_to_user(conn, job_id, session.user_id)
    return service.get_job(conn, job_id, _tz(request))


@router.post('/jobs/{job_id}/assign', summary='Assign an artisan to a job in order_confirmed (staff)')
def assign_job(job_id: int, body: JobAssign, request: Request, _: StaffUser, conn: ConnDep) -> dict[str, Any]:
    return service.assign(conn, job_id, body, _tz(request))


@router.post('/jobs/{job_id}/status', summary='Move a job along the production sequence (staff)')
def change_status(job_id: int, body: StatusChange, request: Request, _: StaffUser, conn: ConnDep) -> dict[str, Any]:
    return service.change_status(conn, job_id, body.status, _tz(request))


@router.post('/jobs/{job_id}/progress', summary='Record progress 0-100 (staff or the assigned artisan)')
def add_progress(job_id: int, body: ProgressIn, request: Request, session: ProductionUser,
                 conn: ConnDep) -> dict[str, Any]:
    if session.role == 'artisan':
        service.assert_job_assigned_to_user(conn, job_id, session.user_id)
    return service.add_progress(conn, job_id, body, session.user_id, _tz(request))
