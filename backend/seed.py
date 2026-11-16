"""Seed_Script: rich, repeatable DEMO data (Req 29).

Usage (from the repository root, with DATABASE_PATH set):

    python -m backend.seed             # seed an empty / unseeded database
    python -m backend.seed --reset     # delete demo rows only (after typing RESET-DEMO), then seed again

Exit codes: 0 success, 1 failure (everything rolled back, cause printed), 2 seeded data already exists
(nothing changed), 3 reset cancelled (nothing changed).

Everything runs in ONE transaction. Every record created here has ``is_demo = 1``; synthetic sales history is
stored as orders with ``source = 'synthetic'`` and a deterministic generator (``random.Random(20250101)``).
Opening stock is written without stock-adjustment rows, and the seeded orders do not deduct stock, so the
inventory levels are exactly the figures in ``PRODUCTS``.

Demo account passwords are read from the environment; when a variable is unset a documented DEMO-ONLY default
is used (see ``ACCOUNTS`` below and ``backend/.env.example``). They are never real credentials.

    DEMO_CUSTOMER_PASSWORD  DEMO_SELLER_PASSWORD  DEMO_ADMIN_PASSWORD  DEMO_ARTISAN_PASSWORD
"""
from __future__ import annotations

import math
import os
import random
import sqlite3
import string
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import ConfigError, Settings  # noqa: E402
from app.db import connect, transaction  # noqa: E402
from app.migrations.runner import MigrationError, run_migrations  # noqa: E402
from app.modules.artisans import api as artisans_api  # noqa: E402
from app.modules.inventory import api as inventory_api  # noqa: E402
from app.modules.legacy.api import bundled_catalog  # noqa: E402
from app.modules.notifications import api as notifications_api  # noqa: E402
from app.modules.orders import api as orders_api  # noqa: E402
from app.modules.orders.schemas import NewOrder, NewOrderLine  # noqa: E402
from app.modules.payments import api as payments_api  # noqa: E402
from app.modules.users import api as users_api  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.time_utils import utc_now  # noqa: E402

SYNTHETIC_SEED = 20250101
RESET_WORD = 'RESET-DEMO'
SHIPPING_FEE_SEN = 800
SYNTHETIC_MONTHS = 12
BUNDLED_STOCK = 100  # same opening stock the legacy module gives the bundled products

EXIT_OK, EXIT_FAILED, EXIT_EXISTS, EXIT_CANCELLED = 0, 1, 2, 3
MSG_EXISTS = 'Seeded data already exists'
MSG_CANCELLED = 'Reset cancelled'

# (key, display name, e-mail, role, phone, password env var, documented DEMO-ONLY default)
ACCOUNTS = [
    ('customer1', 'Demo Customer One', 'demo.customer1@example.com', 'customer', '0123456701',
     'DEMO_CUSTOMER_PASSWORD', 'DemoCustomer1!'),
    ('customer2', 'Demo Customer Two', 'demo.customer2@example.com', 'customer', '0123456702',
     'DEMO_CUSTOMER_PASSWORD', 'DemoCustomer1!'),
    ('customer3', 'Demo Customer Three', 'demo.customer3@example.com', 'customer', '0123456703',
     'DEMO_CUSTOMER_PASSWORD', 'DemoCustomer1!'),
    ('seller', 'Demo Seller', 'demo.seller@example.com', 'seller', '0123456710',
     'DEMO_SELLER_PASSWORD', 'DemoSeller1!'),
    ('admin', 'Demo Admin', 'demo.admin@example.com', 'admin', '0123456711',
     'DEMO_ADMIN_PASSWORD', 'DemoAdmin1!'),
    ('artisan', 'Demo Artisan User', 'demo.artisan@example.com', 'artisan', '0123456712',
     'DEMO_ARTISAN_PASSWORD', 'DemoArtisan1!'),
]

# (name, specialisation, availability, story, private phone, private e-mail, private address)
ARTISANS = [
    ('Siti Aminah', 'Batik and fabric printing', 'available',
     'Demo profile. Prints batik panels by hand in small batches.',
     '0191110001', 'siti.demo@example.com', '1 Jalan Demo, Kota Bharu, Kelantan'),
    ('Ahmad Zulkifli', 'Wood and felt toys', 'busy',
     'Demo profile. Makes traditional toys from wood and felt.',
     '0191110002', 'ahmad.demo@example.com', '2 Jalan Demo, Kuala Terengganu, Terengganu'),
    ('Lim Mei Ling', 'Embroidery and gifts', 'available',
     'Demo profile. Embroiders gift sets and greeting pouches.',
     '0191110003', 'mei.demo@example.com', '3 Jalan Demo, George Town, Pulau Pinang'),
    ('Ravi Kumar', 'Woven accessories', 'unavailable',
     'Demo profile. Weaves small accessories on a handloom.',
     '0191110004', 'ravi.demo@example.com', '4 Jalan Demo, Johor Bahru, Johor'),
]

# (id, name, description, category slug, price sen, artisan index, made to order, opening stock, threshold)
PRODUCTS = [
    ('batik-everyday-tote', 'Batik Everyday Tote', 'DEMO. Lined cotton tote with a batik print.',
     'tote-bags', 3800, 0, False, 120, 5),
    ('songket-market-tote', 'Songket Market Tote', 'DEMO. Sturdy market tote trimmed with songket.',
     'tote-bags', 5200, 0, True, 40, 5),
    ('wau-bulan-plush-kite', 'Wau Bulan Plush Kite', 'DEMO. Soft plush kite inspired by the wau bulan.',
     'toys', 2900, 1, False, 85, 5),
    ('gasing-soft-top', 'Gasing Soft Spinning Top', 'DEMO. Felt spinning top for toddlers.',
     'toys', 2200, 1, False, 2, 5),
    ('congkak-felt-game', 'Congkak Felt Game', 'DEMO. Travel-size congkak board made of felt.',
     'toys', 4500, 1, False, 60, 5),
    ('batik-gift-set', 'Batik Gift Set', 'DEMO. Gift box with a batik pouch, coaster and card.',
     'gifts', 6800, 2, True, 25, 5),
    ('keris-bookmark-duo', 'Keris Bookmark Duo', 'DEMO. Two embroidered bookmarks.',
     'gifts', 1800, 2, False, 0, 5),
    ('raya-greeting-pouch', 'Raya Greeting Pouch', 'DEMO. Embroidered pouch for duit raya.',
     'gifts', 3000, 2, True, 200, 5),
    ('tenun-scrunchie-set', 'Tenun Hair Scrunchie Set', 'DEMO. Three woven scrunchies.',
     'accessories', 1600, 3, False, 150, 5),
    ('batik-passport-cover', 'Batik Passport Cover', 'DEMO. Passport cover in batik cotton.',
     'accessories', 3200, 3, False, 5, 5),
    ('mini-coin-purse', 'Mini Coin Purse', 'DEMO. Zip coin purse in printed cotton.',
     'accessories', 1500, 3, False, 300, 5),
]
BUNDLED_SLUG = {'Kids & Toys': 'fabric-books', 'Bags': 'tote-bags', 'Accessories': 'accessories'}

DELIVERY = {'address': 'No. 1, Jalan Demo, Taman Demo, Kuala Lumpur', 'postcode': '50000', 'state': 'Kuala Lumpur'}

# Fulfilment_Status -> timeline after `placed` (cancelled and payment_failed start in that status, like checkout).
TIMELINE = {
    'placed': [], 'confirmed': ['confirmed'], 'preparing': ['confirmed', 'preparing'],
    'shipped': ['confirmed', 'preparing', 'shipped'],
    'delivered': ['confirmed', 'preparing', 'shipped', 'delivered'], 'cancelled': [], 'payment_failed': [],
}

# (fulfilment status, owner key, method, payment status, payment outcome, days ago, [(product, qty)])
APP_ORDERS = [
    ('placed', 'customer1', 'cod', 'pending_cod', 'pending_cod', 1,
     [('batik-everyday-tote', 1), ('wau-bulan-plush-kite', 2)]),
    ('confirmed', 'customer2', 'card', 'paid', 'success', 3,
     [('songket-market-tote', 2), ('mini-coin-purse', 1)]),
    ('preparing', 'customer3', 'fpx', 'paid', 'success', 5,
     [('batik-gift-set', 1), ('raya-greeting-pouch', 5)]),
    ('shipped', 'customer1', 'ewallet', 'paid', 'success', 9,
     [('congkak-felt-game', 1), ('tenun-scrunchie-set', 2)]),
    ('delivered', 'customer2', 'card', 'paid', 'success', 20,
     [('songket-market-tote', 1), ('batik-gift-set', 1)]),
    ('cancelled', 'customer3', 'card', 'cancelled', 'cancelled', 14, [('batik-passport-cover', 1)]),
    ('payment_failed', 'customer1', 'card', 'failed', 'failed', 2, [('keris-bookmark-duo', 1)]),
]

# Production_Status -> (priority, progress percent, artisan index or None, source)
# source: ('order', fulfilment status, product id) or ('custom', custom order key)
JOBS = [
    ('order_confirmed', 'normal', 0, None, ('order', 'confirmed', 'songket-market-tote')),
    ('production_assigned', 'high', 0, 2, ('order', 'preparing', 'batik-gift-set')),
    ('in_production', 'normal', 40, 0, ('custom', 'accepted')),
    ('quality_checking', 'urgent', 90, 2, ('order', 'preparing', 'raya-greeting-pouch')),
    ('completed', 'low', 100, 0, ('order', 'delivered', 'songket-market-tote')),
    ('ready_for_fulfilment', 'normal', 100, 2, ('order', 'delivered', 'batik-gift-set')),
]


class AlreadySeeded(Exception):
    """Demo data from an earlier run is present; nothing may be changed."""


def demo_password(env: Mapping[str, str], variable: str, default: str) -> str:
    value = env.get(variable)
    return value if value else default


# --- helpers -------------------------------------------------------------------------------------------------------

def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _set_demo(conn: sqlite3.Connection, table: str, ids: list[Any]) -> None:
    """Mark rows created through another module's api (which does not set the flag) as demo data."""
    for row_id in ids:
        conn.execute(f'UPDATE {table} SET is_demo = 1 WHERE id = ?', (row_id,))  # table is a fixed literal


def _id_factory(rng: random.Random) -> Callable[[], str]:
    alphabet = string.ascii_uppercase + string.digits
    return lambda: 'SM-' + ''.join(rng.choice(alphabet) for _ in range(orders_api.ORDER_ID_LENGTH))


def seeded_data_exists(conn: sqlite3.Connection) -> bool:
    """True when an earlier run left demo rows. The 4 bundled products are demo rows too, but the legacy module
    inserts them on its own, so they alone do not count as seeded data."""
    queries = (
        'SELECT 1 FROM users WHERE is_demo = 1 LIMIT 1',
        'SELECT 1 FROM artisans WHERE is_demo = 1 LIMIT 1',
        'SELECT 1 FROM production_jobs WHERE is_demo = 1 LIMIT 1',
        'SELECT 1 FROM custom_orders WHERE is_demo = 1 LIMIT 1',
        "SELECT 1 FROM orders WHERE source = 'synthetic' LIMIT 1",
    )
    if any(conn.execute(q).fetchone() is not None for q in queries):
        return True
    bundled = [item['id'] for item in bundled_catalog()]
    marks = ','.join('?' * len(bundled))
    return conn.execute(f'SELECT 1 FROM products WHERE is_demo = 1 AND id NOT IN ({marks}) LIMIT 1',
                        bundled).fetchone() is not None


# --- seeding -------------------------------------------------------------------------------------------------------

def _seed_users(conn: sqlite3.Connection, env: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    users: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for key, name, email, role, phone, variable, default in ACCOUNTS:
        password = demo_password(env, variable, default)
        if password not in hashes:
            hashes[password] = hash_password(password)
        users[key] = users_api.create_user(conn, name=name, email=email, password_hash=hashes[password],
                                           role=role, phone=phone, is_demo=True)
    now = _iso(utc_now())
    for key in ('customer1', 'customer2', 'customer3'):
        user = users[key]
        conn.execute(
            'INSERT INTO addresses (user_id, recipient_name, phone, line1, line2, postcode, city, state, is_default, '
            'created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,1,?,?)',
            (user['id'], user['name'], user['phone'], 'No. 1, Jalan Demo', 'Taman Demo', DELIVERY['postcode'],
             'Kuala Lumpur', DELIVERY['state'], now, now))
    return users


def _seed_artisans(conn: sqlite3.Connection, users: dict[str, dict[str, Any]]) -> list[int]:
    now = _iso(utc_now())
    ids = []
    for name, specialisation, availability, story, phone, email, address in ARTISANS:
        cur = conn.execute(
            'INSERT INTO artisans (name, specialisation, availability, story, private_phone, private_email, '
            'private_address, is_active, is_demo, created_at, updated_at) VALUES (?,?,?,?,?,?,?,1,1,?,?)',
            (name, specialisation, availability, story, phone, email, address, now, now))
        ids.append(int(cur.lastrowid))
    artisans_api.link_user(conn, ids[0], users['artisan']['id'])
    return ids


def _seed_products(conn: sqlite3.Connection, artisan_ids: list[int]) -> dict[str, dict[str, Any]]:
    """The 4 bundled products keep their ids (and any existing row/stock); the rest are new. Returns id -> info."""
    now = _iso(utc_now())
    categories = {r['slug']: int(r['id']) for r in conn.execute('SELECT id, slug FROM categories')}
    catalogue: dict[str, dict[str, Any]] = {}

    for item in bundled_catalog():
        pid = item['id']
        row = conn.execute('SELECT price_sen FROM products WHERE id = ?', (pid,)).fetchone()
        if row is None:
            slug = BUNDLED_SLUG.get(item.get('category'), 'accessories')
            conn.execute(
                'INSERT INTO products (id, name, description, category_id, price_sen, made_to_order, is_active, '
                'legacy_image_url, legacy_product_url, is_demo, created_at, updated_at) '
                'VALUES (?,?,?,?,?,0,1,?,?,1,?,?)',
                (pid, item['name'], item.get('description', ''), categories[slug], int(item['demoPriceSen']),
                 item.get('imageUrl'), item.get('productUrl'), now, now))
            if item.get('imageUrl'):
                conn.execute('INSERT INTO product_images (product_id, external_url, sort_order, is_demo) '
                             'VALUES (?, ?, 0, 1)', (pid, item['imageUrl']))
            price = int(item['demoPriceSen'])
        else:
            conn.execute('UPDATE products SET is_demo = 1 WHERE id = ?', (pid,))
            price = int(row['price_sen'])
        if conn.execute('SELECT 1 FROM stock_levels WHERE product_id = ?', (pid,)).fetchone() is None:
            inventory_api.initialise(conn, pid, None, BUNDLED_STOCK)
        catalogue[pid] = {'id': pid, 'name': item['name'], 'price': price}

    for pid, name, description, slug, price, artisan_index, made_to_order, stock, threshold in PRODUCTS:
        conn.execute(
            'INSERT INTO products (id, name, description, category_id, price_sen, artisan_id, made_to_order, '
            'is_active, is_demo, created_at, updated_at) VALUES (?,?,?,?,?,?,?,1,1,?,?)',
            (pid, name, description, categories[slug], price, artisan_ids[artisan_index], int(made_to_order),
             now, now))
        inventory_api.initialise(conn, pid, None, stock, threshold)  # opening stock: no adjustment row
        catalogue[pid] = {'id': pid, 'name': name, 'price': price}
    return catalogue


def _new_order(users: dict[str, dict[str, Any]], owner: str, key: str, catalogue: dict[str, dict[str, Any]],
               lines: list[tuple[str, int]], *, method: str, payment_status: str, status: str, source: str,
               created_at: str) -> NewOrder:
    user = users[owner]
    return NewOrder(
        user_id=user['id'], idempotency_key=key, customer_name=user['name'], email=user['email'],
        phone=user['phone'], delivery_address=DELIVERY['address'], delivery_postcode=DELIVERY['postcode'],
        delivery_state=DELIVERY['state'], payment_method=method, payment_status=payment_status, status=status,
        shipping_fee_sen=SHIPPING_FEE_SEN, source=source, is_demo=1, created_at=created_at,
        lines=[NewOrderLine(product_id=pid, variation_id=None, sku_key=pid, name=catalogue[pid]['name'],
                            variation_label=None, unit_price_sen=catalogue[pid]['price'], quantity=qty)
               for pid, qty in lines])


def _advance(conn: sqlite3.Connection, order_id: str, start: str, steps: list[str], first_at: datetime) -> None:
    """Move an order through its timeline, one history row per step, an hour apart."""
    previous, moment = start, first_at
    for step in steps:
        moment += timedelta(hours=1)
        orders_api.update_fields(conn, order_id, status=step, updated_at=_iso(moment))
        orders_api.append_history(conn, order_id, previous, step, None, None, _iso(moment))
        if step == 'shipped':
            orders_api.update_fields(conn, order_id, shipping_reference=f'DEMO-TRACK-{order_id[-6:]}')
        previous = step


def _seed_app_orders(conn: sqlite3.Connection, users: dict[str, dict[str, Any]],
                     catalogue: dict[str, dict[str, Any]], rng: random.Random, now: datetime
                     ) -> dict[str, dict[str, Any]]:
    """One order per Fulfilment_Status. Returns fulfilment status -> order dict."""
    factory = _id_factory(rng)
    result: dict[str, dict[str, Any]] = {}
    for status, owner, method, payment_status, outcome, days_ago, lines in APP_ORDERS:
        created = now - timedelta(days=days_ago)
        order, _ = orders_api.create_order(
            conn, _new_order(users, owner, f'seed-app-{status}', catalogue, lines, method=method,
                             payment_status=payment_status, source='app',
                             status=status if status in ('cancelled', 'payment_failed') else 'placed',
                             created_at=_iso(created)),
            id_factory=factory)
        payments_api.record(conn, order['id'], method, outcome, order['totalSen'], _iso(created))
        _advance(conn, order['id'], 'placed', TIMELINE[status], created)
        if status in ('cancelled', 'payment_failed'):
            orders_api.mark_stock_restored(conn, order['id'])  # nothing was held; keeps restore a no-op
        result[status] = orders_api.get_order(conn, order['id'])  # type: ignore[assignment]
    return result


def _seed_synthetic_sales(conn: sqlite3.Connection, users: dict[str, dict[str, Any]],
                          catalogue: dict[str, dict[str, Any]], rng: random.Random, now: datetime) -> int:
    """12 consecutive months ending on the run date, at least one sale per month. Returns orders created."""
    factory = _id_factory(rng)
    product_ids = list(catalogue)
    base = {pid: rng.randint(2, 9) for pid in product_ids}
    phase = {pid: rng.uniform(0, 2 * math.pi) for pid in product_ids}
    customers = [k for k in users if k.startswith('customer')]
    created_orders = 0
    for index in range(SYNTHETIC_MONTHS):
        back = SYNTHETIC_MONTHS - 1 - index
        year, month = now.year, now.month - back
        while month < 1:
            month += 12
            year -= 1
        last_day = now.day if back == 0 else 27
        quantities = {}
        for pid in product_ids:
            season = 1 + 0.25 * math.sin(2 * math.pi * index / 12 + phase[pid])
            quantities[pid] = max(0, min(20, round(base[pid] * season * (1 + 0.02 * index) + rng.gauss(0, 1))))
        if not any(quantities.values()):
            quantities[product_ids[0]] = 1
        buckets: list[list[tuple[str, int]]] = [[], [], []]
        for pid, qty in quantities.items():
            if qty:
                buckets[rng.randrange(3)].append((pid, qty))
        if not any(buckets):
            continue
        if not buckets[0]:  # keep bucket 0 populated so the month always has a sale
            donor = max(buckets, key=len)
            buckets[0].append(donor.pop())
        for number, lines in enumerate(b for b in buckets if b):
            day = rng.randint(1, last_day)
            # 03:00 to 10:00 UTC stays inside the same calendar month in the app time zone (UTC+8).
            created = min(datetime(year, month, day, rng.randint(3, 10), rng.randint(0, 59),
                                   tzinfo=timezone.utc), now)
            order, _ = orders_api.create_order(
                conn, _new_order(users, rng.choice(customers), f'seed-syn-{index:02d}-{number}', catalogue, lines,
                                 method='card', payment_status='paid', status='placed', source='synthetic',
                                 created_at=_iso(created)),
                id_factory=factory)
            _advance(conn, order['id'], 'placed', TIMELINE['delivered'], created)
            created_orders += 1
    return created_orders


def _seed_custom_orders(conn: sqlite3.Connection, users: dict[str, dict[str, Any]], artisan_ids: list[int],
                        now: datetime) -> dict[str, int]:
    stamp = _iso(now - timedelta(days=4))
    due = (now + timedelta(days=30)).date().isoformat()
    ids: dict[str, int] = {}
    for key, owner, status, ptype, desc, qty, estimate, artisan in (
            ('submitted', 'customer1', 'submitted', 'Tote bag',
             'DEMO request: tote bag with the name of our school embroidered on the front.', 30, None, None),
            ('accepted', 'customer2', 'in_progress', 'Gift pouch',
             'DEMO request: gift pouches in batik for a wedding, 50 pieces in two colours.', 50, 125000,
             artisan_ids[0])):
        cur = conn.execute(
            'INSERT INTO custom_orders (user_id, product_type, description, quantity, preferred_date, status, '
            'estimated_price_sen, artisan_id, is_demo, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,1,?,?)',
            (users[owner]['id'], ptype, desc, qty, due, status, estimate, artisan, stamp, stamp))
        ids[key] = int(cur.lastrowid)
    return ids


def _seed_jobs(conn: sqlite3.Connection, orders: dict[str, dict[str, Any]], custom: dict[str, int],
               artisan_ids: list[int], catalogue: dict[str, dict[str, Any]], now: datetime) -> list[int]:
    """One Production_Job per Production_Status, linked to seeded orders and the accepted custom order."""
    deadline = (now + timedelta(days=21)).date().isoformat()
    stamp = _iso(now - timedelta(days=2))
    job_ids = []
    for status, priority, progress, artisan_index, source in JOBS:
        order_id = line_id = custom_id = product_id = None
        quantity = 1
        if source[0] == 'order':
            order = orders[source[1]]
            line = next(ln for ln in order['lines'] if ln['productId'] == source[2])
            order_id, line_id, product_id, quantity = order['id'], line['id'], line['productId'], line['quantity']
        else:
            custom_id, quantity = custom[source[1]], 50
        cur = conn.execute(
            'INSERT INTO production_jobs (order_id, order_line_id, custom_order_id, product_id, artisan_id, '
            'quantity, deadline, priority, status, progress_percent, notes, is_demo, created_at, updated_at) '
            "VALUES (?,?,?,?,?,?,?,?,?,?,'DEMO job',1,?,?)",
            (order_id, line_id, custom_id, product_id,
             artisan_ids[artisan_index] if artisan_index is not None else None, quantity, deadline, priority,
             status, progress, stamp, stamp))
        job_id = int(cur.lastrowid)
        if progress:
            conn.execute('INSERT INTO production_progress (job_id, percent, note, actor_user_id, created_at) '
                         'VALUES (?,?,?,NULL,?)', (job_id, progress, 'DEMO progress update', stamp))
        if custom_id is not None:
            conn.execute('UPDATE custom_orders SET production_job_id = ? WHERE id = ?', (job_id, custom_id))
        job_ids.append(job_id)
    return job_ids


def _seed_notifications(conn: sqlite3.Connection, users: dict[str, dict[str, Any]],
                        orders: dict[str, dict[str, Any]], custom: dict[str, int]) -> int:
    ids = [
        notifications_api.create(conn, users['customer2']['id'], 'order', 'Order update',
                                 f"Your order {orders['shipped']['id']} is now shipped.",
                                 ('order', orders['shipped']['id'])),
        notifications_api.create(conn, users['customer2']['id'], 'custom_order', 'Custom order update',
                                 f"Your custom order {custom['accepted']} is now in_progress.",
                                 ('custom_order', str(custom['accepted']))),
        notifications_api.create(conn, users['seller']['id'], 'low_stock', 'Low stock',
                                 'Gasing Soft Spinning Top is at or below its low-stock threshold.',
                                 ('product', 'gasing-soft-top')),
        notifications_api.create(conn, users['admin']['id'], 'system', 'Demo data loaded',
                                 'The demo database was seeded. Every record is marked as demo data.'),
    ]
    _set_demo(conn, 'notifications', ids)
    return len(ids)


def seed_all(conn: sqlite3.Connection, env: Mapping[str, str], now: Optional[datetime] = None) -> dict[str, int]:
    """Create every demo record inside the caller's transaction and return a summary of the counts."""
    moment = (now or utc_now()).astimezone(timezone.utc)
    rng = random.Random(SYNTHETIC_SEED)
    users = _seed_users(conn, env)
    artisan_ids = _seed_artisans(conn, users)
    catalogue = _seed_products(conn, artisan_ids)
    orders = _seed_app_orders(conn, users, catalogue, rng, moment)
    synthetic = _seed_synthetic_sales(conn, users, catalogue, rng, moment)
    custom = _seed_custom_orders(conn, users, artisan_ids, moment)
    jobs = _seed_jobs(conn, orders, custom, artisan_ids, catalogue, moment)
    notifications = _seed_notifications(conn, users, orders, custom)
    return {'users': len(users), 'artisans': len(artisan_ids), 'products': len(catalogue), 'orders': len(orders),
            'synthetic_orders': synthetic, 'custom_orders': len(custom), 'production_jobs': len(jobs),
            'notifications': notifications}


# --- reset ---------------------------------------------------------------------------------------------------------

_DEMO_ORDERS = "SELECT id FROM orders WHERE is_demo = 1 AND source <> 'legacy'"
_DEMO_USERS = 'SELECT id FROM users WHERE is_demo = 1'


def delete_demo_data(conn: sqlite3.Connection) -> None:
    """Delete only demo rows, children first. Legacy orders (and the products they use) are never touched; the 4
    bundled products stay so their ids and legacy stock survive. Runs in the caller's transaction."""
    # Give back any stock still held by the demo orders before their ledger rows disappear.
    for row in conn.execute(_DEMO_ORDERS).fetchall():
        inventory_api.restore_for_order(conn, row['id'])

    keep = [item['id'] for item in bundled_catalog()]
    keep_marks = ','.join('?' * len(keep))
    doomed_products = (f"SELECT id FROM products WHERE is_demo = 1 AND id NOT IN ({keep_marks}) AND id NOT IN "
                       f"(SELECT l.product_id FROM order_lines l JOIN orders o ON o.id = l.order_id "
                       f"WHERE o.source = 'legacy')")

    conn.execute(f'DELETE FROM payments WHERE order_id IN ({_DEMO_ORDERS})')
    conn.execute(f'DELETE FROM stock_adjustments WHERE order_id IN ({_DEMO_ORDERS})')
    conn.execute(f'DELETE FROM order_lines WHERE order_id IN ({_DEMO_ORDERS})')
    # order_history is append-only by trigger; lift the delete guard for this transaction only (DDL is transactional).
    trigger = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'order_history_no_delete'"
                           ).fetchone()
    if trigger is not None:
        conn.execute('DROP TRIGGER order_history_no_delete')
    try:
        conn.execute(f'DELETE FROM order_history WHERE order_id IN ({_DEMO_ORDERS})')
    finally:
        if trigger is not None:
            conn.execute(trigger['sql'])
    conn.execute(f'DELETE FROM orders WHERE id IN ({_DEMO_ORDERS})')

    conn.execute('DELETE FROM production_progress WHERE job_id IN (SELECT id FROM production_jobs WHERE is_demo = 1)')
    conn.execute('DELETE FROM production_jobs WHERE is_demo = 1')
    conn.execute('DELETE FROM custom_order_images WHERE custom_order_id IN '
                 '(SELECT id FROM custom_orders WHERE is_demo = 1)')
    conn.execute('DELETE FROM custom_orders WHERE is_demo = 1')

    conn.execute(f'DELETE FROM stock_adjustments WHERE product_id IN ({doomed_products})', keep)
    conn.execute(f'DELETE FROM stock_levels WHERE product_id IN ({doomed_products})', keep)
    conn.execute(f'DELETE FROM inventory_settings WHERE product_id IN ({doomed_products})', keep)
    conn.execute(f'DELETE FROM cart_lines WHERE product_id IN ({doomed_products})', keep)
    conn.execute(f'DELETE FROM favourites WHERE product_id IN ({doomed_products})', keep)
    conn.execute(f'DELETE FROM product_variations WHERE product_id IN ({doomed_products})', keep)
    conn.execute(f'DELETE FROM product_images WHERE product_id IN ({doomed_products})', keep)
    conn.execute('UPDATE products SET artisan_id = NULL WHERE artisan_id IN (SELECT id FROM artisans WHERE is_demo = 1)')
    conn.execute(f'DELETE FROM products WHERE id IN ({doomed_products})', keep)

    conn.execute('DELETE FROM artisans WHERE is_demo = 1')
    for table in ('cart_lines', 'favourites', 'notifications', 'sessions', 'addresses'):
        conn.execute(f'DELETE FROM {table} WHERE user_id IN ({_DEMO_USERS})')  # fixed table names
    conn.execute(f'DELETE FROM login_attempts WHERE email_lower IN (SELECT email_lower FROM users WHERE is_demo = 1)')
    conn.execute('DELETE FROM notifications WHERE is_demo = 1')
    conn.execute('DELETE FROM users WHERE is_demo = 1')


# --- command line --------------------------------------------------------------------------------------------------

def _err(message: str) -> None:
    print(message, file=sys.stderr)


def main(argv: Optional[list[str]] = None, *, environ: Optional[Mapping[str, str]] = None,
         input_fn: Callable[[str], str] = input, now: Optional[datetime] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    env = os.environ if environ is None else environ
    if args not in ([], ['--reset']):
        _err('Usage: python -m backend.seed [--reset]')
        return EXIT_FAILED
    reset = args == ['--reset']
    try:
        settings = Settings.from_env(env)
    except ConfigError as exc:
        _err(str(exc))
        return EXIT_FAILED

    if reset:  # confirm before anything is touched
        try:
            answer = input_fn(f'This deletes all demo data and seeds it again. Type {RESET_WORD} to continue: ')
        except EOFError:
            answer = ''
        if answer != RESET_WORD:
            _err(MSG_CANCELLED)
            return EXIT_CANCELLED

    try:
        run_migrations(settings.database_path)
        conn = connect(settings.database_path)
    except (MigrationError, sqlite3.Error, OSError) as exc:
        _err(f'Seeding failed: {exc}')
        return EXIT_FAILED
    try:
        with transaction(conn):
            if reset:
                delete_demo_data(conn)
            elif seeded_data_exists(conn):
                raise AlreadySeeded()
            summary = seed_all(conn, env, now)
    except AlreadySeeded:
        _err(MSG_EXISTS)
        return EXIT_EXISTS
    except Exception as exc:  # noqa: BLE001 - everything is rolled back; report the cause
        _err(f'Seeding failed: {exc}')
        return EXIT_FAILED
    finally:
        conn.close()
    print('Seeded demo data: ' + ', '.join(f'{k}={v}' for k, v in summary.items()))
    print('All records are DEMO data. Demo logins use the DEMO_*_PASSWORD variables or the documented defaults.')
    return EXIT_OK


if __name__ == '__main__':
    raise SystemExit(main())
