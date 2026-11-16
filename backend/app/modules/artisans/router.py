"""Artisan endpoints: staff management (Req 23.1 to 23.4, 23.6, 23.7), public profiles (23.5) and the product link.
Private contact details are served only by the staff routes, which return 401/403 to everyone else (23.8)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.modules.auth.deps import ConnDep, require_staff
from app.pagination import PageDep

from . import service
from .schemas import ArtisanIn, ProductArtisanLink

staff_router = APIRouter(prefix='/api/staff', tags=['staff-artisans'], dependencies=[Depends(require_staff)])
public_router = APIRouter(prefix='/api/artisans', tags=['artisans'])


@staff_router.get('/artisans', summary='List artisans with private contact details')
def list_artisans(conn: ConnDep, page: PageDep) -> dict[str, Any]:
    items, total = service.list_staff(conn, page)
    return {'items': items, 'total': total, 'limit': page.limit, 'offset': page.offset}


@staff_router.post('/artisans', status_code=201, summary='Create an artisan')
def create_artisan(body: ArtisanIn, conn: ConnDep) -> dict[str, Any]:
    return service.create(conn, body)


@staff_router.get('/artisans/{artisan_id}', summary='Artisan profile, assigned products and job counts')
def get_artisan(artisan_id: int, conn: ConnDep) -> dict[str, Any]:
    return service.get_staff(conn, artisan_id)


@staff_router.put('/artisans/{artisan_id}', summary='Edit an artisan (warns when unavailable with open jobs)')
def update_artisan(artisan_id: int, body: ArtisanIn, conn: ConnDep) -> dict[str, Any]:
    return service.update(conn, artisan_id, body)


@staff_router.put('/products/{product_id}/artisan', summary='Link or unlink (artisanId null) a product and an artisan')
def link_product(product_id: str, body: ProductArtisanLink, conn: ConnDep) -> dict[str, Any]:
    return service.link_product(conn, product_id, body.artisanId)


@public_router.get('', summary='Public artisan profiles')
def list_public(conn: ConnDep, page: PageDep) -> dict[str, Any]:
    items, total = service.list_public(conn, page)
    return {'items': items, 'total': total, 'limit': page.limit, 'offset': page.offset}


@public_router.get('/{artisan_id}', summary='Public artisan profile')
def get_public(artisan_id: int, conn: ConnDep) -> dict[str, Any]:
    return service.get_public(conn, artisan_id)
