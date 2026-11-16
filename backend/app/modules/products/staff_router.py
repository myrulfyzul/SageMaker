"""Staff product management endpoints (Req 20.1 to 20.10). Staff = seller or admin; others get 403."""
from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile

from app.pagination import Page, PageDep

from ..auth.deps import ConnDep, require_staff
from . import staff_service as service
from .schemas import ProductOut
from .staff_schemas import ActiveUpdate, ProductCreate, ProductUpdate

router = APIRouter(prefix='/api/staff/products', tags=['staff-products'], dependencies=[Depends(require_staff)])


@router.get('', response_model=Page[ProductOut], summary='List products, including inactive ones')
def list_products(
    conn: ConnDep,
    page: PageDep,
    q: Annotated[Optional[str], Query(max_length=100, description='Substring of name or description')] = None,
    category: Annotated[Optional[str], Query(max_length=100)] = None,
    active: Annotated[Optional[bool], Query(description='Filter by active flag')] = None,
) -> Any:
    items, total = service.list_products(conn, search=q or None, category=category or None, active=active, page=page)
    return Page.build(items, total, page)


@router.post('', status_code=201, response_model=ProductOut, summary='Create a product')
def create_product(body: ProductCreate, conn: ConnDep) -> Any:
    return service.create_product(conn, body)


@router.get('/{product_id}', response_model=ProductOut)
def get_product(product_id: str, conn: ConnDep) -> Any:
    return service.get_product(conn, product_id)


@router.put('/{product_id}', response_model=ProductOut, summary='Edit a product')
def update_product(product_id: str, body: ProductUpdate, conn: ConnDep) -> Any:
    return service.update_product(conn, product_id, body)


@router.delete('/{product_id}', status_code=204, summary='Delete a product that is in no order')
def delete_product(product_id: str, conn: ConnDep, request: Request) -> Response:
    service.delete_product(conn, product_id, request.app.state.settings.media_dir)
    return Response(status_code=204)


@router.patch('/{product_id}/active', response_model=ProductOut, summary='Activate or deactivate a product')
def set_active(product_id: str, body: ActiveUpdate, conn: ConnDep) -> Any:
    return service.set_active(conn, product_id, body)


@router.post('/{product_id}/images', status_code=201, response_model=ProductOut, summary='Upload a product image')
def upload_image(product_id: str, conn: ConnDep, request: Request, file: Annotated[UploadFile, File()]) -> Any:
    return service.add_image(conn, product_id, file.filename or '', file.file, request.app.state.settings.media_dir)
