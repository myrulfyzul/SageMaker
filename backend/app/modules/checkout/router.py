"""HTTP layer for checkout.

`POST /api/checkout`: customer only; simulated payments need DEMO_MODE=1, and with a real gateway configured only
cash on delivery may use it. The hosted-gateway endpoints live under `/api/payments`.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from app.errors import AppError
from app.modules.auth.deps import ConnDep, require_customer
from app.modules.auth.api import SessionInfo
from app.modules.payments import api as payments_api

from . import gateway_service, service
from .schemas import CheckoutIn, GatewayStartIn

router = APIRouter(prefix='/api', tags=['checkout'])
CustomerDep = Annotated[SessionInfo, Depends(require_customer)]


class InvalidWebhook(AppError):
    status = 400
    code = 'invalid_signature'
    message = 'The webhook signature is not valid'


@router.post('/checkout', status_code=201, dependencies=[Depends(payments_api.require_demo_mode)],
             summary='Place an order from the cart (cash on delivery, or simulated payment without a gateway)')
def checkout(body: CheckoutIn, request: Request, session: CustomerDep, conn: ConnDep) -> JSONResponse:
    payments_api.reject_simulated_when_gateway(request.app.state.settings, body.method)
    order, created = service.place_order(conn, session.user_id, body)
    return JSONResponse(order, status_code=201 if created else 200)


@router.get('/payments/config', summary='Which payment gateway this server uses')
def payment_config(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return {
        'gateway': 'stripe' if settings.gateway_enabled else 'prototype',
        'sandbox': True,
        'methods': payments_api.gateway_methods(settings, request.app.state.payment_gateway),
        'ewalletProvider': payments_api.GATEWAY_EWALLET if settings.gateway_enabled else None,
    }


@router.post('/payments/sessions', status_code=201, summary='Start a payment on the hosted gateway page')
def start_payment(body: GatewayStartIn, request: Request, session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return gateway_service.start(conn, request.app.state.settings, request.app.state.payment_gateway,
                                 session.user_id, body)


@router.get('/payments/sessions/{session_id}', summary='Status of a payment; confirms it with the gateway')
def payment_status(session_id: str, request: Request, session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return gateway_service.get_for_user(conn, request.app.state.settings, request.app.state.payment_gateway,
                                        session.user_id, session_id)


@router.post('/payments/sessions/{session_id}/cancel', summary='Give up on a pending payment')
def cancel_payment(session_id: str, request: Request, session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return gateway_service.cancel(conn, request.app.state.settings, request.app.state.payment_gateway,
                                  session.user_id, session_id)


@router.post('/payments/webhook/stripe', include_in_schema=False)
async def stripe_webhook(request: Request, conn: ConnDep) -> dict[str, bool]:
    settings = request.app.state.settings
    if not settings.stripe_webhook_secret:
        raise payments_api.PaymentsNotConfigured('The webhook secret is not configured.')
    payload = await request.body()
    try:
        event = payments_api.verify_webhook(payload, request.headers.get('stripe-signature'),
                                            settings.stripe_webhook_secret)
    except payments_api.WebhookSignatureError:
        raise InvalidWebhook() from None
    # The handler reads the session back from Stripe (blocking), so keep it off the event loop.
    await run_in_threadpool(gateway_service.handle_webhook, conn, settings, request.app.state.payment_gateway, event)
    return {'received': True}


@router.get('/payments/return', response_class=HTMLResponse, include_in_schema=False)
def payment_return(request: Request, conn: ConnDep, s: Annotated[str, Query(max_length=40)],
                   cancelled: int = 0) -> HTMLResponse:
    status, page = gateway_service.return_page(conn, request.app.state.settings, request.app.state.payment_gateway,
                                               s, bool(cancelled))
    return HTMLResponse(page, status_code=status, headers={'Cache-Control': 'no-store'})
