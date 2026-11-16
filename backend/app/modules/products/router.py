"""Public catalogue endpoints (Req 9.1 to 9.9, 9.14, 28.8)."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Query

from app.pagination import Page, PageDep

from ..auth.deps import ConnDep, OptionalSessionDep
from . import service
from .schemas import ProductOut

router = APIRouter(prefix='/api/products', tags=['products'])

home_router = APIRouter(prefix='/api/home', tags=['home'])

STAFF_ROLES = frozenset({'seller', 'admin'})


@home_router.get('/best-sellers', response_model=list[ProductOut], summary='Best sellers (last 90 days)')
def best_sellers(conn: ConnDep) -> Any:
    return service.best_sellers(conn)


@home_router.get('/new-arrivals', response_model=list[ProductOut], summary='New arrivals')
def new_arrivals(conn: ConnDep) -> Any:
    return service.new_arrivals(conn)


@home_router.get('/recommendations', response_model=list[ProductOut],
                 summary='Recommendations (optional auth; falls back to best sellers)')
def recommendations(conn: ConnDep, session: OptionalSessionDep) -> Any:
    return service.recommendations(conn, session.user_id if session is not None else None)


@router.get('', response_model=Page[ProductOut], summary='List active products')
def list_products(
    conn: ConnDep,
    page: PageDep,
    q: Annotated[Optional[str], Query(max_length=100, description='Case-insensitive substring of name or description')] = None,
    category: Annotated[Optional[str], Query(max_length=100, description='Category slug or id')] = None,
    sort: Annotated[Optional[Literal['price_asc', 'price_desc']], Query(description='Price order; ties by name')] = None,
) -> Any:
    items, total = service.list_products(conn, search=q or None, category=category or None, sort=sort, page=page)
    return Page.build(items, total, page)


@router.get('/{product_id}', response_model=ProductOut, summary='Product detail')
def get_product(product_id: str, conn: ConnDep, session: OptionalSessionDep) -> Any:
    is_staff = session is not None and session.role in STAFF_ROLES
    return service.get_product(conn, product_id, is_staff=is_staff)
