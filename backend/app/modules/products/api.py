"""The only surface other modules may import from `products`. All functions take the caller's open connection."""
from __future__ import annotations

import sqlite3
from typing import Any, Iterable

from app.errors import NotFound

from app.modules.categories import api as categories_api

from . import service


def active_product_ids(conn: sqlite3.Connection, product_ids: Iterable[str]) -> set[str]:
    """Subset of `product_ids` that exist and are active."""
    ids = list(dict.fromkeys(product_ids))
    found: set[str] = set()
    for start in range(0, len(ids), 500):  # stay under SQLite's variable limit
        chunk = ids[start:start + 500]
        marks = ','.join('?' * len(chunk))
        rows = conn.execute(f'SELECT id FROM products WHERE is_active = 1 AND id IN ({marks})', chunk).fetchall()
        found.update(r['id'] for r in rows)
    return found


def get_product(conn: sqlite3.Connection, product_id: str, *, is_staff: bool) -> dict[str, Any]:
    """Product DTO; raises NotFound for a missing product (or an inactive one when not is_staff)."""
    return service.get_product(conn, product_id, is_staff=is_staff)


def get_active_products(conn: sqlite3.Connection, product_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Public product DTOs for the active products among `product_ids`, in the given order.
    Missing and inactive ids are omitted."""
    result = []
    for pid in product_ids:
        try:
            result.append(service.get_product(conn, pid, is_staff=False))
        except NotFound:
            continue
    return result


def get_sellable(conn: sqlite3.Connection, product_id: str, variation_id: Any = None) -> dict[str, Any] | None:
    """Current server price and state of one product (or one of its variations) for the cart.

    Returns None when the product (or the named variation) does not exist. `active` is False when the product or the
    variation is inactive. `unitPriceSen` is the base price plus the variation delta, in integer sen.
    """
    row = conn.execute('SELECT name, price_sen, is_active FROM products WHERE id = ?', (product_id,)).fetchone()
    if row is None:
        return None
    price = int(row['price_sen'])
    active = bool(row['is_active'])
    label = None
    if variation_id is not None:
        var = conn.execute('SELECT label, price_delta_sen, is_active FROM product_variations '
                           'WHERE id = ? AND product_id = ?', (variation_id, product_id)).fetchone()
        if var is None:
            return None
        price += int(var['price_delta_sen'])
        active = active and bool(var['is_active'])
        label = var['label']
    img = conn.execute('SELECT filename, external_url FROM product_images WHERE product_id = ? '
                       'ORDER BY sort_order, id LIMIT 1', (product_id,)).fetchone()
    image_url = None
    if img is not None:
        image_url = (service.MEDIA_PREFIX + img['filename']) if img['filename'] else img['external_url']
    return {'productId': product_id, 'variationId': variation_id, 'name': row['name'], 'variationLabel': label,
            'unitPriceSen': price, 'active': active, 'imageUrl': image_url}


def product_names(conn: sqlite3.Connection, product_ids: Iterable[str]) -> dict[str, str]:
    """`id -> name` for the existing products among `product_ids` (active or not)."""
    ids = list(dict.fromkeys(product_ids))
    names: dict[str, str] = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        marks = ','.join('?' * len(chunk))
        for r in conn.execute(f'SELECT id, name FROM products WHERE id IN ({marks})', chunk).fetchall():
            names[r['id']] = r['name']
    return names


def made_to_order_ids(conn: sqlite3.Connection, product_ids: Iterable[str]) -> set[str]:
    """Subset of `product_ids` whose product is flagged made to order (Req 24.1)."""
    ids = list(dict.fromkeys(product_ids))
    found: set[str] = set()
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        marks = ','.join('?' * len(chunk))
        rows = conn.execute(f'SELECT id FROM products WHERE made_to_order = 1 AND id IN ({marks})', chunk).fetchall()
        found.update(r['id'] for r in rows)
    return found


def products_for_artisan(conn: sqlite3.Connection, artisan_id: int) -> list[dict[str, Any]]:
    """Products linked to an artisan (active or not), by name: `[{id, name, isActive}]`."""
    rows = conn.execute('SELECT id, name, is_active FROM products WHERE artisan_id = ? '
                        'ORDER BY name COLLATE NOCASE, id', (artisan_id,)).fetchall()
    return [{'id': r['id'], 'name': r['name'], 'isActive': bool(r['is_active'])} for r in rows]


def set_product_artisan(conn: sqlite3.Connection, product_id: str, artisan_id: int | None) -> int | None:
    """Link (or with None unlink) a product and an artisan; returns the previous artisan id.
    Raises NotFound for an unknown product. Runs in the caller's transaction."""
    from app.time_utils import utc_now_iso
    row = conn.execute('SELECT artisan_id FROM products WHERE id = ?', (product_id,)).fetchone()
    if row is None:
        raise NotFound('Product not found')
    conn.execute('UPDATE products SET artisan_id = ?, updated_at = ? WHERE id = ?',
                 (artisan_id, utc_now_iso(), product_id))
    return row['artisan_id']


def variation_labels(conn: sqlite3.Connection, product_id: str) -> dict[int, str]:
    """`variation id -> label` for one product."""
    rows = conn.execute('SELECT id, label FROM product_variations WHERE product_id = ?', (product_id,)).fetchall()
    return {int(r['id']): r['label'] for r in rows}


# --- Legacy catalogue (/api/legacy, Req 1.1) ----------------------------------------------------------------------

# Reverse of the seed mapping: new category slug -> the old category string kept in legacy output.
LEGACY_CATEGORY_BY_SLUG = {'tote-bags': 'Bags', 'fabric-books': 'Kids & Toys', 'toys': 'Kids & Toys',
                           'gifts': 'Accessories', 'accessories': 'Accessories'}
_SLUG_BY_LEGACY_CATEGORY = {'Kids & Toys': 'fabric-books', 'Bags': 'tote-bags', 'Accessories': 'accessories'}


def legacy_catalogue(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Active products in the legacy `assets/products.json` shape, in creation order."""
    rows = conn.execute(
        'SELECT id, name, description, price_sen, legacy_image_url, legacy_product_url, category_id '
        'FROM products WHERE is_active = 1 ORDER BY rowid').fetchall()
    cats = categories_api.by_ids(conn, [r['category_id'] for r in rows])
    # an inner join dropped products whose category is missing; keep that behaviour
    rows = [r for r in rows if r['category_id'] in cats]
    return [{'id': r['id'], 'name': r['name'],
             'category': LEGACY_CATEGORY_BY_SLUG.get(cats[r['category_id']]['slug'], cats[r['category_id']]['name']),
             'description': r['description'], 'imageUrl': r['legacy_image_url'] or '',
             'productUrl': r['legacy_product_url'] or '', 'demoPriceSen': int(r['price_sen'])} for r in rows]


def ensure_legacy_catalogue(conn: sqlite3.Connection, items: Iterable[dict[str, Any]]) -> list[str]:
    """Insert the bundled legacy products (ids preserved) when the products table is completely empty, so a
    freshly migrated database can serve `/api/legacy` before the seed script has run. Returns the inserted ids
    (the caller creates their stock rows). Runs in the caller's transaction."""
    if conn.execute('SELECT 1 FROM products LIMIT 1').fetchone() is not None:
        return []
    from app.time_utils import utc_now_iso
    now = utc_now_iso()
    inserted = []
    for item in items:
        slug = _SLUG_BY_LEGACY_CATEGORY.get(item.get('category'), 'accessories')
        cat_id = categories_api.id_by_slug(conn, slug)
        if cat_id is None:
            continue
        conn.execute(
            'INSERT INTO products (id, name, description, category_id, price_sen, made_to_order, is_active, '
            'legacy_image_url, legacy_product_url, is_demo, created_at, updated_at) '
            'VALUES (?, ?, ?, ?, ?, 0, 1, ?, ?, 1, ?, ?)',
            (item['id'], item['name'], item.get('description', ''), cat_id, int(item['demoPriceSen']),
             item.get('imageUrl'), item.get('productUrl'), now, now))
        if item.get('imageUrl'):
            conn.execute('INSERT INTO product_images (product_id, external_url, sort_order, is_demo) '
                         'VALUES (?, ?, 0, 1)', (item['id'], item['imageUrl']))
        inserted.append(item['id'])
    return inserted


def category_names_by_product(conn: sqlite3.Connection) -> dict[str, str]:
    """`product id -> category name` for every product (used by analytics for the inventory distribution)."""
    rows = conn.execute('SELECT id, category_id FROM products').fetchall()
    cats = categories_api.by_ids(conn, [r['category_id'] for r in rows])
    return {r['id']: cats[r['category_id']]['name'] for r in rows if r['category_id'] in cats}
