"""HTTP layer for /api/auth."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response

from . import service
from .deps import ConnDep, SessionDep
from .schemas import LoginOut, LoginRequest, RegisterRequest, SessionOut, UserOut

router = APIRouter(prefix='/api/auth', tags=['auth'])


@router.post('/register', status_code=201, response_model=UserOut)
def register(body: RegisterRequest, conn: ConnDep) -> dict[str, Any]:
    return service.register(conn, body)


@router.post('/login', response_model=LoginOut)
def login(body: LoginRequest, request: Request, conn: ConnDep) -> dict[str, Any]:
    return service.login(conn, body, request.app.state.settings.token_lifetime_seconds)


@router.post('/logout', status_code=204)
def logout(session: SessionDep, conn: ConnDep) -> Response:
    service.logout(conn, session.session_id)
    return Response(status_code=204)


@router.get('/session', response_model=SessionOut)
def get_session(session: SessionDep) -> dict[str, Any]:
    return {'user': {'id': session.user_id, 'name': session.name, 'email': session.email, 'role': session.role},
            'role': session.role, 'expiresAt': session.expires_at}
