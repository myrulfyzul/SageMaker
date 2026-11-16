"""Product read side: list, detail and the public DTO."""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from app.errors import NotFound
from app.modules.inventory import api as inventory_api
from app.pagination import PageParams

from app.modules.artisans import api as artisans_api
from app.modules.categories import api as categories_api

from . import repository as repo

MEDIA_PREFIX = '/media/'


def stock_status(quantity: int, threshold: int) -> dict[str, Any]:
    """Req 9.11: In stock above the threshold, Low stock at or below it (above zero), Out of stock at zero."""
    if quantity <= 0:
        return {'status': 'out_of_stock', 'quantity': 0, 'label': 'Out of stock'}
    if quantity <= threshold:
        return {'status': 'low_stock', 'quantity': quantity, 'label': f'Low stock: {quantity} left'}
    return {'status': 'in_stock', 'quantity': quantity, 'label': 'In stock'}


def _stock(conn: sqlite3.Connection, product_id: str) -> tuple[dict[str, Any], dict[int, int]]:
    try:
        level = inventory_api.get_level(conn, product_id)
    except NotFound:  # no stock record means nothing to sell
        return stock_status(0, 0), {}
    per_variation = {v['variationId']: v['quantity'] for v in level['variations']}
    return stock_status(level['quantity'], level['lowStockThreshold']), per_variation


def _image_url(row: sqlite3.Row) -> Optional[str]:
    if row['filename']:
        return MEDIA_PREFIX + row['filename']
    return row['external_url']


def _dto(conn: sqlite3.Connection, row: sqlite3.Row, variations: list[sqlite3.Row], images: list[sqlite3.Row]) -> dict[str, Any]:
    stock, per_variation = _stock(conn, row['id'])
    price = int(row['price_sen'])
    artisan_name = artisans_api.public_name(conn, row['artisan_id'])
    return {
        'id': row['id'],
        'name': row['name'],
        'description': row['description'],
        'category': categories_api.by_ids(conn, [row['category_id']]).get(row['category_id']) or {'id': row['category_id'], 'slug': None, 'name': None},
        'priceSen': price,
        'demoPriceSen': price,
        'isDemo': bool(row['is_demo']),
        'isActive': bool(row['is_active']),
        'madeToOrder': bool(row['made_to_order']),
        'images': [{'id': i['id'], 'url': _image_url(i), 'isDemo': bool(i['is_demo'])} for i in images],
        'variations': [{'id': v['id'], 'label': v['label'], 'priceDeltaSen': int(v['price_delta_sen']),
                        'priceSen': price + int(v['price_delta_sen']), 'isActive': bool(v['is_active']),
                        'stockQuantity': per_variation.get(v['id'], 0)} for v in variations],
        'stock': stock,
        'artisan': ({'id': row['artisan_id'], 'name': artisan_name} if artisan_name else None),
    }


def category_filter(conn: sqlite3.Connection, category: Optional[str]) -> Optional[list[int]]:
    """Category ids matching a slug or numeric-id filter; None when no filter was given."""
    return categories_api.ids_matching(conn, category) if category else None


def list_products(conn: sqlite3.Connection, *, search: Optional[str], category: Optional[str],
                  sort: Optional[str], page: PageParams) -> tuple[list[dict[str, Any]], int]:
    rows, total = repo.list_active(conn, search=search, category_ids=category_filter(conn, category), sort=sort,
                                   limit=page.limit, offset=page.offset)
    ids = [r['id'] for r in rows]
    variations = repo.variations_for(conn, ids, include_inactive=False)
    images = repo.images_for(conn, ids)
    return [_dto(conn, r, variations[r['id']], images[r['id']]) for r in rows], total


HOME_LIMIT = 10
BEST_SELLER_DAYS = 90


def _dtos_for(conn: sqlite3.Connection, ids: list[str]) -> list[dict[str, Any]]:
    """Public DTOs for active products, in the order of `ids`."""
    variations = repo.variations_for(conn, ids, include_inactive=False)
    images = repo.images_for(conn, ids)
    out = []
    for pid in ids:
        row = repo.get_by_id(conn, pid)
        out.append(_dto(conn, row, variations[pid], images[pid]))
    return out


def _ranked_best_sellers(conn: sqlite3.Connection, *, categories: Optional[set[int]] = None,
                         exclude: frozenset[str] = frozenset()) -> list[str]:
    """Active product ids ordered by units sold in the last 90 days desc, then created_at desc, then id."""
    from app.modules.orders import api as orders_api  # local import: orders.api is a sibling module surface
    units = orders_api.units_sold_since(conn, days=BEST_SELLER_DAYS)
    rows = conn.execute('SELECT id, category_id, created_at FROM products WHERE is_active = 1').fetchall()
    rows = [r for r in rows if r['id'] not in exclude and (categories is None or r['category_id'] in categories)]
    rows.sort(key=lambda r: r['id'])
    rows.sort(key=lambda r: r['created_at'], reverse=True)
    rows.sort(key=lambda r: units.get(r['id'], 0), reverse=True)
    return [r['id'] for r in rows[:HOME_LIMIT]]


def best_sellers(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return _dtos_for(conn, _ranked_best_sellers(conn))


def new_arrivals(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute('SELECT id FROM products WHERE is_active = 1 ORDER BY created_at DESC, id ASC LIMIT ?',
                        (HOME_LIMIT,)).fetchall()
    return _dtos_for(conn, [r['id'] for r in rows])


def recommendations(conn: sqlite3.Connection, user_id: Optional[int]) -> list[dict[str, Any]]:
    """Active products from the categories of favourites and purchases, minus purchased ones (Req 8.4).
    Visitors and users without signal get best sellers in the same order (Req 8.5)."""
    if user_id is None:
        return best_sellers(conn)
    from app.modules.orders import api as orders_api
    from app.modules.users import api as users_api
    favourites = set(users_api.favourite_product_ids(conn, user_id))
    purchased = orders_api.purchased_product_ids(conn, user_id)
    signal = sorted(favourites | purchased)
    if not signal:
        return best_sellers(conn)
    marks = ','.join('?' * len(signal))
    categories = {r['category_id'] for r in conn.execute(
        f'SELECT DISTINCT category_id FROM products WHERE id IN ({marks})', signal)}
    return _dtos_for(conn, _ranked_best_sellers(conn, categories=categories, exclude=frozenset(purchased)))


def get_product(conn: sqlite3.Connection, product_id: str, *, is_staff: bool) -> dict[str, Any]:
    """404 for a missing product, or an inactive one when the requester is not a Staff_User (Req 9.14)."""
    row = repo.get_by_id(conn, product_id)
    if row is None or (not row['is_active'] and not is_staff):
        raise NotFound('Product not found')
    variations = repo.variations_for(conn, [product_id], include_inactive=is_staff)[product_id]
    images = repo.images_for(conn, [product_id])[product_id]
    return _dto(conn, row, variations, images)
