"""AppError hierarchy, the error envelope and the exception handlers."""
from __future__ import annotations

import logging
import sqlite3
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger('sagemaker.errors')

GENERIC_MESSAGE = 'An unexpected error occurred'


class AppError(Exception):
    status = 400
    code = 'bad_request'
    message = 'Bad request'

    def __init__(self, message: Optional[str] = None, *, code: Optional[str] = None,
                 status: Optional[int] = None, details: Optional[list[Any]] = None,
                 headers: Optional[dict[str, str]] = None):
        self.message = message or self.message
        self.code = code or self.code
        self.status = status or self.status
        self.details = details
        self.headers = headers
        super().__init__(self.message)


class ValidationFailed(AppError):
    status = 422
    code = 'validation_error'
    message = 'Request validation failed'

    def __init__(self, details: list[Any], message: Optional[str] = None, **kw: Any):
        super().__init__(message, details=details, **kw)


class Unauthenticated(AppError):
    status = 401
    code = 'unauthenticated'
    message = 'Authentication required'


class Forbidden(AppError):
    status = 403
    code = 'forbidden'
    message = 'You do not have permission to perform this action'


class NotFound(AppError):
    status = 404
    code = 'not_found'
    message = 'Resource not found'


class Conflict(AppError):
    status = 409
    code = 'conflict'
    message = 'Request conflicts with the current state'


def envelope(code: str, message: str, details: Optional[list[Any]] = None) -> dict[str, Any]:
    error: dict[str, Any] = {'code': code, 'message': message}
    if details is not None:
        error['details'] = details
    return {'error': error}


_HTTP_CODES = {
    400: 'bad_request', 401: 'unauthenticated', 403: 'forbidden', 404: 'not_found',
    405: 'method_not_allowed', 409: 'conflict', 413: 'payload_too_large',
    415: 'unsupported_media_type', 429: 'too_many_requests', 503: 'unavailable',
}
_HTTP_MESSAGES = {
    401: 'Authentication required', 403: 'You do not have permission to perform this action',
    404: 'Resource not found', 405: 'Method not allowed',
}


def _field_name(loc: Any) -> str:
    parts = [str(p) for p in loc if p not in ('body', 'query', 'path', 'header', 'cookie')]
    return '.'.join(parts) if parts else str(loc[0]) if loc else 'request'


def validation_details(exc: RequestValidationError) -> list[dict[str, str]]:
    return [{'field': _field_name(err.get('loc', ())), 'reason': str(err.get('msg', 'invalid value'))}
            for err in exc.errors()]


async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(envelope(exc.code, exc.message, exc.details), status_code=exc.status, headers=exc.headers)


async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(envelope('validation_error', 'Request validation failed', validation_details(exc)), status_code=422)


async def _http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_CODES.get(exc.status_code, 'http_error')
    message = _HTTP_MESSAGES.get(exc.status_code) or (exc.detail if isinstance(exc.detail, str) and exc.detail else 'Request failed')
    return JSONResponse(envelope(code, message), status_code=exc.status_code, headers=getattr(exc, 'headers', None))


async def _busy_handler(_: Request, exc: sqlite3.OperationalError) -> JSONResponse:
    if 'locked' in str(exc).lower() or 'busy' in str(exc).lower():
        return JSONResponse(envelope('busy', 'The service is busy, please retry'), status_code=503, headers={'Retry-After': '1'})
    return await _unexpected_handler(_, exc)


async def _unexpected_handler(_: Request, exc: Exception) -> JSONResponse:
    # Logged server-side only; the response never carries class names, paths or SQL.
    logger.error('Unhandled exception', exc_info=(type(exc), exc, exc.__traceback__))
    return JSONResponse(envelope('internal_error', GENERIC_MESSAGE), status_code=500)


def register_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(sqlite3.OperationalError, _busy_handler)
    app.add_exception_handler(Exception, _unexpected_handler)
