"""HTTP layer for /api/me (customer) and /api/users (admin).

This is also the composition point for deactivation: users marks the account inactive and auth revokes the
sessions, both in one transaction, without the two modules importing each other's internals."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from ..auth import api as auth_api
from ..auth.deps import ConnDep, require_admin, require_customer
from ..auth.api import SessionInfo
from . import service
from .schemas import AddressInput, AddressOut, FavouritesMerge, ProfileOut, ProfileUpdate, RoleChange

me_router = APIRouter(prefix='/api/me', tags=['profile'])
favourites_router = APIRouter(prefix='/api/favourites', tags=['favourites'])
admin_router = APIRouter(prefix='/api/users', tags=['users'])

CustomerDep = Annotated[SessionInfo, Depends(require_customer)]
AdminDep = Annotated[SessionInfo, Depends(require_admin)]


@me_router.get('', response_model=ProfileOut)
def get_profile(session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return service.get_user(conn, session.user_id)


@me_router.put('', response_model=ProfileOut)
def update_profile(body: ProfileUpdate, session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return service.update_profile(conn, session.user_id, body)


@me_router.get('/addresses', response_model=list[AddressOut])
def list_addresses(session: CustomerDep, conn: ConnDep) -> list[dict[str, Any]]:
    return service.list_addresses(conn, session.user_id)


@me_router.post('/addresses', status_code=201, response_model=AddressOut)
def create_address(body: AddressInput, session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return service.create_address(conn, session.user_id, body)


@me_router.put('/addresses/{address_id}/default', response_model=AddressOut)
def set_default_address(address_id: int, session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return service.set_default_address(conn, session.user_id, address_id)


@me_router.put('/addresses/{address_id}', response_model=AddressOut)
def update_address(address_id: int, body: AddressInput, session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    return service.update_address(conn, session.user_id, address_id, body)


@me_router.delete('/addresses/{address_id}', status_code=204)
def delete_address(address_id: int, session: CustomerDep, conn: ConnDep) -> Response:
    service.delete_address(conn, session.user_id, address_id)
    return Response(status_code=204)


@favourites_router.get('')
def list_favourites(session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    items = service.list_favourites(conn, session.user_id)
    return {'items': items, 'total': len(items)}


@favourites_router.post('/merge')
def merge_favourites(body: FavouritesMerge, session: CustomerDep, conn: ConnDep) -> dict[str, Any]:
    items = service.merge_favourites(conn, session.user_id, body.product_ids)
    return {'items': items, 'total': len(items)}


@favourites_router.put('/{product_id}', status_code=204)
def add_favourite(product_id: str, session: CustomerDep, conn: ConnDep) -> Response:
    service.add_favourite(conn, session.user_id, product_id)
    return Response(status_code=204)


@favourites_router.delete('/{product_id}', status_code=204)
def remove_favourite(product_id: str, session: CustomerDep, conn: ConnDep) -> Response:
    service.remove_favourite(conn, session.user_id, product_id)
    return Response(status_code=204)


@admin_router.patch('/{user_id}/role', response_model=ProfileOut)
def change_role(user_id: int, body: RoleChange, _: AdminDep, conn: ConnDep) -> dict[str, Any]:
    return service.change_role(conn, user_id, body.role)


@admin_router.post('/{user_id}/deactivate', response_model=ProfileOut)
def deactivate(user_id: int, _: AdminDep, conn: ConnDep) -> dict[str, Any]:
    return service.deactivate_user(conn, user_id, within=lambda c: auth_api.revoke_user_sessions(c, user_id))
