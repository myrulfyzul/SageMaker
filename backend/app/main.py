"""Application factory: middleware, handlers, health route and OpenAPI docs."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import ConfigError, Settings
from .errors import register_handlers
from .logging_setup import configure_logging
from .migrations.runner import MigrationError, run_migrations
from .modules.analytics.router import router as analytics_router
from .modules.artisans.router import public_router as public_artisans_router
from .modules.artisans.router import staff_router as staff_artisans_router
from .modules.auth.router import router as auth_router
from .modules.cart.router import router as cart_router
from .modules.checkout.router import router as checkout_router
from .modules.categories.router import router as categories_router
from .modules.custom_orders.router import media_router as custom_order_media_router
from .modules.custom_orders.router import router as custom_orders_router
from .modules.custom_orders.router import staff_router as staff_custom_orders_router
from .modules.forecasting.router import router as forecasting_router
from .modules.legacy import router as legacy_router
from .modules.inventory.router import router as staff_inventory_router
from .modules.orders.router import router as orders_router, staff_router as staff_orders_router
from .modules.notifications.router import router as notifications_router
from .modules.payments.router import router as payments_router
from .modules.production.router import router as production_router
from .modules.products.router import home_router as products_home_router
from .modules.products.router import router as products_router
from .modules.products.staff_router import router as staff_products_router
from .modules.settings.router import router as staff_settings_router
from .modules.users.router import admin_router as users_admin_router, me_router as users_me_router
from .modules.users.router import favourites_router as users_favourites_router

SERVICE_NAME = 'sagemaker-prototype'
CORS_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
CORS_HEADERS = ['Content-Type', 'Authorization', 'X-Order-Token', 'X-Admin-Key']


class NoSniffASGI:
    """Outermost ASGI wrapper: adds X-Content-Type-Options: nosniff to every response,
    including those produced by the server-error middleware."""

    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        async def send_with_header(message: Any) -> None:
            if message['type'] == 'http.response.start':
                headers = [(k, v) for k, v in message.get('headers', []) if k.lower() != b'x-content-type-options']
                headers.append((b'x-content-type-options', b'nosniff'))
                message = {**message, 'headers': headers}
            await send(message)

        await self.app(scope, receive, send_with_header)

    def __getattr__(self, name: str) -> Any:  # expose FastAPI attributes (state, routes, ...)
        return getattr(self.app, name)


def _health_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix='/api', tags=['health'])

    @router.get('/health', summary='Service status (no database access)')
    def health() -> dict[str, Any]:
        return {'ok': True, 'service': SERVICE_NAME, 'demoMode': settings.demo_mode}

    return router


def create_app(settings: Settings) -> NoSniffASGI:
    configure_logging()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            run_migrations(settings.database_path)
        except MigrationError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from None
        yield

    app = FastAPI(
        title='SageMaker API',
        version='1.0',
        description='SageMaker Asia commerce and operations API. Payments run through a prototype gateway.',
        docs_url='/docs',
        openapi_url='/openapi.json',
        lifespan=lifespan,
    )
    app.state.settings = settings
    register_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=CORS_METHODS,
        allow_headers=CORS_HEADERS,
        allow_credentials=False,
    )
    app.include_router(_health_router(settings))
    app.include_router(auth_router)
    app.include_router(users_me_router)
    app.include_router(users_admin_router)
    app.include_router(categories_router)
    app.include_router(products_router)
    app.include_router(products_home_router)
    app.include_router(staff_products_router)
    app.include_router(legacy_router)
    app.include_router(users_favourites_router)
    app.include_router(payments_router)
    app.include_router(cart_router)
    app.include_router(checkout_router)
    app.include_router(orders_router)
    app.include_router(staff_orders_router)
    app.include_router(staff_inventory_router)
    app.include_router(staff_artisans_router)
    app.include_router(public_artisans_router)
    app.include_router(production_router)
    app.include_router(custom_orders_router)
    app.include_router(custom_order_media_router)
    app.include_router(staff_custom_orders_router)
    app.include_router(notifications_router)
    app.include_router(staff_settings_router)
    app.include_router(analytics_router)
    app.include_router(forecasting_router)
    return NoSniffASGI(app)


def __getattr__(name: str) -> Any:
    """Lazy `application` built from the environment; exits 1 naming the bad variable."""
    if name == 'application':
        try:
            built = create_app(Settings.from_env())
        except ConfigError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from None
        globals()['application'] = built
        return built
    raise AttributeError(name)
