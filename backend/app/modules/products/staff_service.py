"""Staff product management: create, edit, activate, delete and image upload (Req 20.1 to 20.10)."""
from __future__ import annotations

import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Any, BinaryIO, Optional

from app import db, uploads
from app.errors import Conflict, NotFound, ValidationFailed
from app.modules.artisans import api as artisans_api
from app.modules.categories import api as categories_api
from app.modules.inventory import api as inventory_api
from app.modules.orders import api as orders_api
from app.modules.settings import api as settings_api
from app.pagination import PageParams
from app.time_utils import utc_now_iso

from . import repository as repo, service
from .staff_schemas import ActiveUpdate, ProductCreate, ProductUpdate, VariationIn

logger = logging.getLogger('sagemaker.products')


def _invalid(field: str, reason: str) -> ValidationFailed:
    return ValidationFailed([{'field': field, 'reason': reason}])


def _check_references(conn: sqlite3.Connection, category_id: int, artisan_id: Optional[int]) -> None:
    errors = []
    if not categories_api.exists(conn, category_id):
        errors.append({'field': 'categoryId', 'reason': 'unknown category'})
    if artisan_id is not None and not artisans_api.exists(conn, artisan_id):
        errors.append({'field': 'artisanId', 'reason': 'unknown artisan'})
    if errors:
        raise ValidationFailed(errors)


def _check_variation_prices(price: int, variations: list[VariationIn]) -> None:
    for i, v in enumerate(variations):
        if price + v.priceDeltaSen < 1:
            raise _invalid(f'variations.{i}.priceDeltaSen', 'variation price must be at least 1 sen')


def _detail(conn: sqlite3.Connection, product_id: str) -> dict[str, Any]:
    return service.get_product(conn, product_id, is_staff=True)


def _require(conn: sqlite3.Connection, product_id: str) -> sqlite3.Row:
    row = repo.get_by_id(conn, product_id)
    if row is None:
        raise NotFound('Product not found')
    return row


def list_products(conn: sqlite3.Connection, *, search: Optional[str], category: Optional[str],
                  active: Optional[bool], page: PageParams) -> tuple[list[dict[str, Any]], int]:
    rows, total = repo.list_for_staff(conn, search=search, category_ids=service.category_filter(conn, category), active=active,
                                      limit=page.limit, offset=page.offset)
    return [_detail(conn, r['id']) for r in rows], total


def get_product(conn: sqlite3.Connection, product_id: str) -> dict[str, Any]:
    return _detail(conn, product_id)


def create_product(conn: sqlite3.Connection, body: ProductCreate) -> dict[str, Any]:
    if body.variations and body.stock:
        raise _invalid('stock', 'use per-variation stock when variations are given')
    _check_variation_prices(body.priceSen, body.variations)
    product_id = 'P-' + uuid.uuid4().hex[:12]
    now = utc_now_iso()
    with db.transaction(conn):
        threshold = (settings_api.get_default_low_stock_threshold(conn)
                     if body.lowStockThreshold is None else body.lowStockThreshold)
        _check_references(conn, body.categoryId, body.artisanId)
        repo.insert_product(conn, product_id=product_id, name=body.name, description=body.description,
                            category_id=body.categoryId, price_sen=body.priceSen, artisan_id=body.artisanId,
                            made_to_order=body.madeToOrder, now=now)
        if body.variations:
            for v in body.variations:
                vid = repo.insert_variation(conn, product_id, v.label, v.priceDeltaSen, v.isActive)
                inventory_api.initialise(conn, product_id, vid, v.stock or 0, threshold)
        else:
            inventory_api.initialise(conn, product_id, None, body.stock, threshold)
    return _detail(conn, product_id)


def _sync_variations(conn: sqlite3.Connection, product_id: str, price: int, incoming: list[VariationIn],
                     threshold: int) -> None:
    existing = {int(r['id']): r for r in repo.all_variations(conn, product_id)}
    kept: set[int] = set()
    for i, v in enumerate(incoming):
        if v.id is not None:
            if v.id not in existing:
                raise _invalid(f'variations.{i}.id', 'variation does not belong to this product')
            if v.stock is not None:
                raise _invalid(f'variations.{i}.stock', 'change stock through inventory adjustments')
            repo.update_variation(conn, v.id, v.label, v.priceDeltaSen, v.isActive)
            kept.add(v.id)
    for i, v in enumerate(incoming):
        if v.id is None:
            if not existing and inventory_api.get_level(conn, product_id)['quantity'] > 0:
                raise _invalid(f'variations.{i}', 'cannot add variations while the product has base stock')
            vid = repo.insert_variation(conn, product_id, v.label, v.priceDeltaSen, v.isActive)
            inventory_api.initialise(conn, product_id, vid, v.stock or 0, threshold)
            kept.add(vid)
    for vid, row in existing.items():
        if vid not in kept and row['is_active']:
            repo.update_variation(conn, vid, row['label'], int(row['price_delta_sen']), False)


def update_product(conn: sqlite3.Connection, product_id: str, body: ProductUpdate) -> dict[str, Any]:
    _check_variation_prices(body.priceSen, body.variations or [])
    now = utc_now_iso()
    with db.transaction(conn):
        row = _require(conn, product_id)
        link_given = 'artisanId' in body.model_fields_set
        artisan_id = body.artisanId if link_given else row['artisan_id']
        _check_references(conn, body.categoryId, artisan_id if link_given else None)
        fields: dict[str, object] = {'name': body.name, 'category_id': body.categoryId,
                                     'price_sen': body.priceSen, 'artisan_id': artisan_id}
        if body.description is not None:
            fields['description'] = body.description
        if body.madeToOrder is not None:
            fields['made_to_order'] = int(body.madeToOrder)
        repo.update_product(conn, product_id, fields, now)
        threshold = body.lowStockThreshold
        if threshold is not None:
            inventory_api.set_threshold(conn, product_id, threshold)
        if body.variations is not None:
            _sync_variations(conn, product_id, body.priceSen, body.variations,
                             threshold if threshold is not None
                             else settings_api.get_default_low_stock_threshold(conn))
    return _detail(conn, product_id)


def set_active(conn: sqlite3.Connection, product_id: str, body: ActiveUpdate) -> dict[str, Any]:
    with db.transaction(conn):
        _require(conn, product_id)
        repo.set_active(conn, product_id, body.isActive, utc_now_iso())
    return _detail(conn, product_id)


def delete_product(conn: sqlite3.Connection, product_id: str, media_dir: Optional[Path]) -> None:
    """Permanent delete only when no order line references the product (Req 20.8, 20.9)."""
    with db.transaction(conn):
        _require(conn, product_id)
        if orders_api.product_in_any_order(conn, product_id):
            raise Conflict('This product appears in at least one order and cannot be deleted. Deactivate it instead.',
                           code='product_in_orders')
        files = repo.delete_product(conn, product_id)
        inventory_api.remove_for_product(conn, product_id)
    if media_dir is not None:
        for name in files:
            try:
                (Path(media_dir) / name).unlink(missing_ok=True)
            except OSError:
                logger.warning('Could not remove image file for deleted product')


def add_image(conn: sqlite3.Connection, product_id: str, filename: str, stream: BinaryIO,
              media_dir: Path) -> dict[str, Any]:
    """Validate, store and attach an image. On rejection existing images are unchanged (Req 20.5, 20.6)."""
    _require(conn, product_id)
    data = uploads.read_limited(stream)
    ext = uploads.validate_image(filename, data)
    stored = uploads.store_image(media_dir, data, ext)
    try:
        with db.transaction(conn):
            _require(conn, product_id)
            repo.insert_image(conn, product_id, stored)
    except BaseException:
        (Path(media_dir) / stored).unlink(missing_ok=True)
        raise
    return _detail(conn, product_id)
