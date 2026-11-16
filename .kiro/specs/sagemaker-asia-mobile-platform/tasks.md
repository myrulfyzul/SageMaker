# Implementation Plan: Sagemaker Asia Mobile Platform

## Overview

This plan migrates the existing prototype (single-file `lib/main.dart`, single-file `backend/server.py`) into a modular FastAPI backend (Python, SQLite, pytest, Hypothesis) and a feature-based Flutter app (Dart, Riverpod, go_router, glados). It follows the design's rollout order: stabilise and migrate, backend auth/RBAC, catalogue, cart/checkout/payments/orders, inventory, artisans/production/custom orders, notifications, analytics/forecasting, Flutter shell, customer features, staff features, seed script, README, then integration and end-to-end tests.

Two sequencing notes that follow from module dependencies:

- The inventory core (stock levels, reserve, restore) and the notifications core (create and helper functions) are built just before the first module that calls them. Their staff endpoints, adjustments and routers are completed in their own sections later.
- Calls from `orders` to `production.api` (job creation on confirm) are wired in the production section, once that module exists.

## Tasks

- [x] 1. Stabilise the backend and add the migration framework
  - [x] 1.1 Create backend scaffolding and cross-cutting components
    - Add `backend/app/` with `config.py` (`Settings.from_env`, strict validation, no fallback secrets), `db.py` (`connect`, `transaction()` using `BEGIN IMMEDIATE`, PRAGMA foreign_keys), `errors.py` (AppError hierarchy, error envelope, handlers for validation, HTTP and bare exceptions), `money.py`, `time_utils.py`, `pagination.py` (`PageParams`, `Page` envelope), `logging_setup.py` (redaction filter) and `main.py` (`create_app(settings)`, NoSniff ASGI wrapper, CORS allow-list, `GET /api/health`, OpenAPI at `/docs` and `/openapi.json`)
    - Update `backend/requirements.txt` (pydantic, email-validator, python-multipart, argon2-cffi, pandas, numpy, all version-constrained) and add `backend/requirements-dev.txt` (pytest, httpx, hypothesis)
    - Add `.env.example` with `DATABASE_PATH`, `ALLOWED_ORIGINS`, `TOKEN_LIFETIME_SECONDS`, `DEMO_MODE`, `MEDIA_DIR`, `APP_TIMEZONE` and `tests/conftest.py` with a temporary database per run that is deleted at teardown
    - _Requirements: 1.6, 1.8, 1.9, 1.11, 2.7, 2.8, 2.9, 28.1, 28.2, 28.3, 28.4, 28.5, 28.6, 28.7, 28.8, 28.9, 31.5, 31.6, 32.9, 33.2_

  - [x] 1.2 Implement the Migration_Runner and CLI
    - Create `migrations/runner.py`: `schema_migrations` bootstrap, sorted pending versions, one-time pre-migration `.bak` copy of the database file, per-version `BEGIN IMMEDIATE`, statement-by-statement execution with `sqlite3.complete_statement`, version insert in the same transaction, rollback and `MigrationError` naming the failed version
    - Support `.sql` and `.py` (`up(conn)`) versions; start-up in `lifespan` exits with code 1 and `Migration failed: <version>: <cause>`
    - Add `backend/migrate.py` (`status`, `up`)
    - _Requirements: 1.2, 1.3, 1.4, 1.5_

  - [x] 1.3 Write migrations 0001 to 0011
    - Add `versions/0001_baseline.sql` (`CREATE TABLE IF NOT EXISTS orders`, identical to `server.py`) through `0011_indexes.sql` exactly as in the design schema: users/sessions/login_attempts/addresses, categories (5 seed rows)/products/variations/images, inventory tables, add-only `ALTER TABLE orders` plus `order_lines`/`order_history` with append-only triggers, cart/favourites, payments, artisans/production, custom orders, notifications/app_settings, indexes
    - No migration may `UPDATE` or `DELETE` legacy `orders` rows
    - _Requirements: 1.2, 1.3, 1.11, 9.13, 14.1, 14.7, 21.7_

  - [x] 1.4 Create the legacy compatibility module and keep the old tests green
    - Add `modules/legacy/` serving `GET /api/legacy/products`, `POST /api/legacy/orders`, `GET /api/legacy/orders/{id}` (`X-Order-Token`), `PATCH /api/legacy/admin/orders/{id}/status` (`X-Admin-Key`) with unchanged request and response shapes, reading prices from `assets/products.json` until the products module exists
    - Replace `backend/server.py` with a shim (`from app.main import application as app`), keep `admin_update.py` pointed at the legacy route, and re-point `backend/test_server.py` through a single `LEGACY_PREFIX` constant with identical inputs and expected outputs
    - _Requirements: 1.1, 1.2, 1.8, 2.7_

  - [x] 1.5 Write property test for migration atomicity and idempotence
    - **Property 1: Migration atomicity and idempotence**
    - **Validates: Requirements 1.3, 1.4, 1.5**

  - [x] 1.6 Write property test for legacy orders surviving migration
    - **Property 2: Legacy orders survive migration unchanged**
    - **Validates: Requirements 1.2**

  - [x] 1.7 Write property tests for money serialisation and configuration validation
    - **Property 3: Money values serialise as JSON integers**
    - **Property 4: Configuration validation names the offending variable**
    - **Validates: Requirements 1.8, 1.9, 1.11**

  - [x] 1.8 Write property tests for CORS and safe error responses
    - **Property 6: CORS allow-list**
    - **Property 42: Safe error responses**
    - **Validates: Requirements 2.7, 2.8, 28.4, 33.2**

  - [x] 1.9 Add the repository secret scan test
    - Add a test that scans `lib/`, `assets/`, `backend/` and config files for hard-coded passwords, admin keys and tokens and fails on any match
    - _Requirements: 1.9, 1.10_

- [x] 2. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Backend authentication, users and RBAC
  - [x] 3.1 Implement security helpers and log redaction
    - Add `security.py`: argon2id hashing and verification, `secrets.token_urlsafe(32)` tokens, SHA-256 token hashing, `hmac.compare_digest`, dummy-hash verification for unknown emails
    - Wire the redaction filter for `password`, `password_hash`, `token`, `token_hash` and Artisan contact values at every log level
    - _Requirements: 4.2, 4.6, 5.4, 33.5_

  - [x] 3.2 Implement the users module core (repository, service, api)
    - Add `modules/users/` repository, schemas and `api.py` (create customer, lookup by `email_lower`, profile read and update, address CRUD with default handling in one transaction, `favourite_product_ids` placeholder, role change and deactivate)
    - Validators: name 1-100, phone 8-15 digits, address fields, 5-digit postcode
    - _Requirements: 4.1, 4.3, 4.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [x] 3.3 Implement the auth module and RBAC_Guard
    - Add `modules/auth/` with `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/session`; registration ignores a supplied role, atomic user creation with 500 `registration_failed` on internal failure
    - Login: generic 401, `login_attempts` lockout (429 with `retry_after_seconds`), session expiry per `TOKEN_LIFETIME_SECONDS` returning `session_expired`
    - Add `deps.py`: `current_session`, `require_roles`, `require_staff`, `require_admin`, `require_customer`, optional-session dependency
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.1, 5.2, 5.3, 5.4, 5.7, 6.1, 6.2, 33.1_

  - [x] 3.4 Expose the users routers
    - Add `GET/PUT /api/me`, `GET/POST /api/me/addresses`, `PUT/DELETE /api/me/addresses/{id}`, `PUT /api/me/addresses/{id}/default` (customer only, ownership filtered in the repository returning identical 404s), `PATCH /api/users/{id}/role` and `POST /api/users/{id}/deactivate` (admin only)
    - Register the auth and users routers in `main.py`
    - _Requirements: 6.3, 6.5, 6.6, 6.9, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [x] 3.5 Write property test for registration validation
    - **Property 7: Registration validation**
    - **Validates: Requirements 4.1, 4.3, 4.4, 4.5**

  - [x] 3.6 Write property test for secrets handling
    - **Property 8: Secrets are never exposed or stored in clear**
    - **Validates: Requirements 4.2, 4.6, 5.4, 33.5**

  - [x] 3.7 Write property tests for lockout, logout and session lifetime
    - **Property 11: Authentication responses and lockout**
    - **Property 43: Session lifetime**
    - **Validates: Requirements 5.2, 5.3, 5.7, 33.1**

  - [x] 3.8 Write property test for the address book default invariant
    - **Property 45: Address book default invariant**
    - **Validates: Requirements 7.6, 7.7**

  - [x] 3.9 Write unit tests for auth, profile and address endpoints
    - Success and failure path for register, login, logout, session, profile and addresses, including 401, 403 and identical 404 bodies
    - _Requirements: 4.1, 4.3, 5.1, 5.2, 6.1, 6.2, 7.2, 7.8, 31.1_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Catalogue: categories, products, images, favourites
  - [x] 5.1 Implement upload validation and the categories module
    - Add `uploads.py` (`validate_image`: extension allow-list, magic bytes matching the extension type, max 5 MB, read at most 5 MB + 1, `uuid4` stored names, temp-write then move)
    - Add `modules/categories/` with `GET /api/categories`
    - _Requirements: 9.13, 20.5, 20.6, 33.3, 33.4_

  - [x] 5.2 Implement the inventory core
    - Add `modules/inventory/` repository and `api.py`: `initialise`, `get_level`, `reserve_for_order` (conditional `UPDATE ... WHERE quantity >= ?`), `restore_for_order` (once only through `orders.api.mark_stock_restored`), `low_stock_count`, `distribution_by_category`, with `stock_levels` `CHECK (quantity >= 0)` and ledger rows in `stock_adjustments`
    - _Requirements: 14.4, 14.5, 14.9, 14.10, 21.1, 21.8_

  - [x] 5.3 Implement the products read side
    - Add `modules/products/` repository, service and router: `GET /api/products` (active only, escaped `LIKE` substring search over name and description, category filter, price sort with name tie-break, `limit`/`offset`, `total`), `GET /api/products/{id}` (404 for missing or inactive unless staff), DTO with `priceSen`, `demoPriceSen`, `isDemo`, variations, stock status and public artisan name
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.14, 28.7, 28.8_

  - [x] 5.4 Implement staff product management
    - Add `GET/POST /api/staff/products`, `GET/PUT/DELETE /api/staff/products/{id}`, `PATCH /api/staff/products/{id}/active`, `POST /api/staff/products/{id}/images`, with field validation (name 1-200, description at most 2000, price 1-99,999,999 sen, category, threshold), initial stock through `inventory.api.initialise`, and delete rule returning 409 `product_in_orders` when the product is in any order (deactivation recommended)
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.7, 20.8, 20.9, 20.10_

  - [x] 5.5 Implement favourites
    - Add `GET /api/favourites`, idempotent `PUT/DELETE /api/favourites/{product_id}`, `POST /api/favourites/merge` in the users module; inactive products are omitted from lists while associations are retained; add of a missing or inactive product returns an unavailable error
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.9, 10.10_

  - [x] 5.6 Write property test for catalogue query semantics
    - **Property 39: Catalogue query semantics**
    - **Validates: Requirements 9.1, 9.2, 9.4, 9.6, 9.7, 9.8, 20.3, 20.4, 28.7**

  - [x] 5.7 Write property test for upload validation
    - **Property 41: Upload validation**
    - **Validates: Requirements 16.2, 16.3, 20.5, 20.6, 33.3, 33.4**

  - [x] 5.8 Write property test for favourites set semantics
    - **Property 44: Favourites set semantics**
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.9, 10.10**

  - [x] 5.9 Write property test for product validators
    - **Property 52: Product and artisan validators** (product part)
    - **Validates: Requirements 20.1, 20.2, 20.7**

  - [x] 5.10 Write unit tests for catalogue and product CRUD
    - Success and failure path for list, search, filter, detail, staff create, edit, delete, deactivate and upload, including 404 for inactive products and 403 for customers
    - _Requirements: 9.1, 9.3, 9.14, 20.9, 20.10, 31.1_

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Cart, checkout, payments and orders
  - [x] 7.1 Implement the notifications core
    - Add `modules/notifications/` repository and `api.py`: `create`, `order_created`, `order_status_changed`, `custom_order_created`, `custom_order_status_changed`, `low_stock` (skips staff with an unread low-stock row for the same product), `production_ready`; all take the caller's open connection
    - _Requirements: 14.8, 16.4, 17.1, 17.2, 17.3, 17.4, 17.5_

  - [x] 7.2 Implement the orders module core
    - Add `modules/orders/` repository, schemas and `api.py`: create order with lines and `items_json`, `SM-` + 10 random characters id with retry on unique violation, `checkout_id` stored as `"{user_id}:{key}"`, `order_history` append, `mark_stock_restored`, `units_sold_since`, `purchased_product_ids`, `product_in_any_order`, `sales_rows`, `monthly_units`; legacy `packing` read as `preparing` and synthetic first history entry on read
    - _Requirements: 14.1, 14.6, 14.7, 15.5, 22.13_

  - [x] 7.3 Implement the cart module
    - Add `modules/cart/` with `GET /api/cart`, `POST/PUT /api/cart/lines`, `DELETE /api/cart/lines/{line_id}`, `POST /api/cart/merge`; server-priced totals, 800 sen delivery when at least one available line, unavailable lines excluded from totals, quantity 1-20 and line cap 20 (422), stock check (409 with `available`), merge result with `notMerged`
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10, 11.12, 11.13_

  - [x] 7.4 Implement the payments module
    - Add `modules/payments/` `record(conn, ...)` and `GET /api/orders/{id}/payments` (owner and staff); request schema with `extra='forbid'` so no card data is accepted; `DEMO_MODE != 1` returns 503 with no record; `is_demo` always 1
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 33.7_

  - [x] 7.5 Implement checkout orchestration
    - Add `modules/checkout/` `POST /api/checkout`: `BEGIN IMMEDIATE`, idempotency lookup (original order returned with 200 and no writes), delivery validation (422), empty cart (400), stock reservation (409 listing each short product), order and payment creation, outcome table (`paid`/`pending_cod`/`payment_failed`/`cancelled` with stock restore), cart clear, customer and staff notifications, all in one transaction
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.8, 12.9, 13.3, 13.4, 13.5, 13.6, 13.7, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8_

  - [x] 7.6 Implement customer order endpoints, payment retry and the staff order state machine
    - Add `GET /api/orders`, `GET /api/orders/{id}` (history timeline, optional `productionLabel`), `POST /api/orders/{id}/payments` (retry from `payment_failed` with stock re-validation and 409 on shortage), `GET /api/staff/orders` (status filter, `q` search, pagination, 422 `invalid_filter`), `GET /api/staff/orders/{id}`, `POST /api/staff/orders/{id}/status` (transitions, `shipping_reference` 3-80, cancel `reason` 3-500, 409 `invalid_transition`, one history row and one notification per real change, restore stock on cancel)
    - _Requirements: 13.11, 13.12, 14.9, 14.10, 15.1, 15.2, 15.3, 15.4, 15.5, 15.8, 15.10, 22.1, 22.2, 22.3, 22.5, 22.6, 22.7, 22.8, 22.9, 22.10, 22.11, 22.12, 22.13_

  - [x] 7.7 Implement home sections
    - Add `GET /api/home/best-sellers`, `GET /api/home/new-arrivals`, `GET /api/home/recommendations` (optional auth, fallback to best sellers) in the products module using `orders.api` and `users.api`
    - _Requirements: 8.2, 8.3, 8.4, 8.5_

  - [x] 7.8 Re-point the legacy module at the new services
    - Make `/api/legacy/*` read products from the products table (reverse category map) and create guest orders (`user_id` NULL, `source='legacy'`, `DEMO-` id, `demo_simulated_not_charged`) through the same stock reservation path; keep status flow `placed→packing→shipped→delivered` and response shapes; show legacy orders in the staff list
    - _Requirements: 1.1, 1.2, 14.4, 22.13_

  - [x] 7.9 Write property test for cart totals
    - **Property 13: Cart totals invariant**
    - **Validates: Requirements 11.4, 11.5, 11.7, 11.10**

  - [x] 7.10 Write property test for cart quantity bounds
    - **Property 14: Cart quantity bounds and stock limits**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.6**

  - [x] 7.11 Write property test for the cart round trip
    - **Property 15: Cart add/remove round trip**
    - **Validates: Requirements 11.8, 11.11**

  - [x] 7.12 Write property test for guest cart merge
    - **Property 16: Guest cart merge**
    - **Validates: Requirements 11.12, 11.13**

  - [x] 7.13 Write property test for delivery and field validators (backend)
    - **Property 17: Delivery and field validators** (Python side)
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.5, 12.3, 12.4, 16.1, 16.8**

  - [x] 7.14 Write property test for order identifier format
    - **Property 18: Order identifier format**
    - **Validates: Requirements 14.1**

  - [x] 7.15 Write property test for stock conservation under concurrency
    - **Property 19: Stock conservation under checkout, including concurrency**
    - **Validates: Requirements 14.3, 14.4, 14.5**

  - [x] 7.16 Write property test for checkout idempotence
    - **Property 20: Checkout idempotence**
    - **Validates: Requirements 12.9, 14.6**

  - [x] 7.17 Write property test for payment outcome mapping
    - **Property 21: Payment outcome mapping**
    - **Validates: Requirements 13.1, 13.3, 13.4, 13.5, 13.6, 13.7, 33.7**

  - [x] 7.18 Write property test for payment retry
    - **Property 22: Payment retry**
    - **Validates: Requirements 13.11, 13.12**

  - [x] 7.19 Write property test for stock restoration exactly once
    - **Property 23: Stock restoration happens exactly once**
    - **Validates: Requirements 14.9, 14.10, 22.11**

  - [x] 7.20 Write property test for the order status state machine
    - **Property 25: Order status state machine**
    - **Validates: Requirements 22.5, 22.6, 22.7, 22.8, 22.9, 22.10, 22.11, 22.13**

  - [x] 7.21 Write property test for one history row and one notification per change
    - **Property 28: One history row and one notification per real status change** (orders part)
    - **Validates: Requirements 15.5, 17.2, 17.4, 22.12**

  - [x] 7.22 Write property test for atomic order creation
    - **Property 50: Atomic order creation** (checkout part, single injected failure at each step)
    - **Validates: Requirements 14.2**

  - [x] 7.23 Write property test for the order line snapshot
    - **Property 51: Order line snapshot**
    - **Validates: Requirements 14.7**

  - [x] 7.24 Write property test for home sections
    - **Property 46: Home sections**
    - **Validates: Requirements 8.2, 8.3, 8.4, 8.5**

  - [x] 7.25 Write unit tests for cart, checkout, payments and orders
    - Success and failure path for cart add and merge, insufficient stock, checkout, payment outcomes, order history, status updates, and the three legacy smoke tests
    - _Requirements: 1.1, 11.6, 12.9, 13.3, 14.5, 15.1, 22.5, 31.1_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Inventory management
  - [x] 9.1 Implement the inventory service and staff endpoints
    - Complete `modules/inventory/` service and router: `GET /api/staff/inventory` (low-stock flag, `low_only` filter, variation sums), `GET /api/staff/inventory/{product_id}`, `POST .../adjustments` (non-zero delta within ±999,999,999, reason 1-255, conditional update, 409 `insufficient_stock`, ledger row), `GET .../adjustments` (history newest first), `PUT .../threshold` (0-999,999,999), and low-stock notification after a decrease
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8, 21.9_

  - [x] 9.2 Write property test for the stock ledger invariant
    - **Property 24: Stock ledger invariant**
    - **Validates: Requirements 14.9, 21.1, 21.2, 21.3, 21.5, 21.8**

  - [x] 9.3 Write unit tests for inventory
    - Success and failure path for adjustment, threshold, history, low-stock flag and 403 for customers
    - _Requirements: 21.2, 21.3, 21.5, 21.7, 31.1_

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Artisans, production and custom orders
  - [x] 11.1 Implement the artisans module
    - Add `modules/artisans/`: staff `GET/POST /api/staff/artisans`, `GET/PUT /api/staff/artisans/{id}` (private contact, assigned products, open and completed job counts), public `GET /api/artisans` and `/api/artisans/{id}` using a separate public serializer, `unavailable` with open jobs succeeding with `warnings`, `PUT /api/staff/products/{id}/artisan` link and unlink
    - _Requirements: 23.1, 23.2, 23.3, 23.4, 23.5, 23.6, 23.7, 23.8_

  - [x] 11.2 Implement the production module
    - Add `modules/production/`: `GET /api/production/jobs` (filters AND-combined, `view=list|board`, computed `overdue`), `GET /api/production/jobs/{id}`, `POST /api/production/jobs` (manual), `POST .../assign` (status `order_confirmed`, quantity 1-999,999, deadline not before today in `APP_TIMEZONE`, priority, notes), `POST .../status` (transition map including `quality_checking→in_production`), `POST .../progress` (0-100, note at most 500, staff or assigned Artisan_User); artisan scoping via `assert_job_assigned_to_user`; `create_jobs_for_order`, `counts_for_artisan`, `open_job_count`; `ready_for_fulfilment` creates a staff notification only
    - _Requirements: 6.7, 6.8, 24.1, 24.2, 24.3, 24.4, 24.5, 24.6, 24.7, 24.8, 24.9, 24.10, 24.11, 24.13_

  - [x] 11.3 Implement the custom orders module
    - Add `modules/custom_orders/`: customer `GET/POST /api/custom-orders` (multipart, up to 5 images, all-or-nothing file handling), `GET /api/custom-orders/{id}`, `GET /api/media/{filename}` (owner or staff), staff `GET /api/staff/custom-orders` (status filter), `accept` (price 1-99,999,999), `reject` (reason 5-500 after trim), `assign-artisan` (active artisan, status `accepted`, assignment and production job in one transaction), `status`; transition map with 409 for others; notifications for staff on create and owner on change
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.8, 25.1, 25.2, 25.3, 25.4, 25.5, 25.6, 25.7, 25.8, 25.10_

  - [x] 11.4 Wire production into order confirmation
    - Call `production.api.create_jobs_for_order` when an order moves to `confirmed` (job per qualifying line: `made_to_order` or quantity above remaining stock), expose `productionLabel` on the customer order detail, and register artisans, production and custom-orders routers in `main.py`
    - _Requirements: 15.10, 24.1, 24.10, 30.3_

  - [x] 11.5 Write property test for the production state machine and independence
    - **Property 26: Production status machine and independence**
    - **Validates: Requirements 24.4, 24.5, 24.10, 24.11**

  - [x] 11.6 Write property test for the custom order state machine
    - **Property 27: Custom order state machine**
    - **Property 28: One history row and one notification per real status change** (custom order part)
    - **Validates: Requirements 17.3, 25.3, 25.4, 25.5, 25.6, 25.10**

  - [x] 11.7 Write property test for production and artisan rules
    - **Property 48: Production and artisan rules**
    - **Validates: Requirements 24.1, 24.3, 24.6, 24.7, 24.8, 24.9, 24.13**

  - [x] 11.8 Write property test for artisan privacy and counts
    - **Property 49: Artisan privacy and counts**
    - **Property 52: Product and artisan validators** (artisan part)
    - **Validates: Requirements 23.1, 23.2, 23.3, 23.4, 23.5, 23.6**

  - [x] 11.9 Write property test for atomic custom-order assignment
    - **Property 50: Atomic order creation** (custom-order assignment and production job persist together or not at all)
    - **Validates: Requirements 25.7, 25.8**

  - [x] 11.10 Write unit tests for artisans, production and custom orders
    - Success and failure path for artisan CRUD, assignment, progress by the assigned and a non-assigned Artisan_User, custom order create, accept, reject and invalid transition
    - _Requirements: 6.7, 6.8, 16.8, 23.8, 24.6, 25.10, 31.1_

- [x] 12. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Notifications
  - [x] 13.1 Complete the notifications service and router
    - Add `GET /api/notifications` (own only, newest first, `unreadCount`), `POST /api/notifications/{id}/read`, `POST /api/notifications/read-all`; Artisan_User excluded; foreign or missing ids return identical 404s; no e-mail, SMS or push; register the router in `main.py`
    - _Requirements: 17.5, 17.6, 17.7, 17.8, 17.11_

  - [x] 13.2 Write property test for notification scoping and low-stock de-duplication
    - **Property 29: Notification scoping and low-stock de-duplication**
    - **Validates: Requirements 17.5, 17.7**

  - [x] 13.3 Write property test for creation notifications
    - **Property 30: Order creation notifications**
    - **Validates: Requirements 14.8, 16.4**

  - [x] 13.4 Write unit tests for notifications
    - Success and failure path for list, unread count, mark one, mark all and foreign id
    - _Requirements: 17.6, 17.7, 17.8, 31.1_

- [x] 14. Analytics, settings and forecasting
  - [x] 14.1 Implement the analytics module
    - Add `modules/analytics/`: `GET /api/staff/analytics/dashboard` (KPIs, `salesByMonth` last 12 months, `ordersByStatus` with all seven keys, top 5 `bestSellers`, `inventoryByCategory`) and `GET /api/staff/analytics/sales?start&end` (revenue, count, AOV round half up, monthly series with zero months, top 5 and bottom 5, 422 `invalid_range` and `range_too_long`); revenue excludes `cancelled` and `payment_failed`; reads only through other modules' `api.py`
    - _Requirements: 19.2, 19.3, 19.5, 19.6, 26.1, 26.2, 26.3, 26.4, 26.6, 26.7_

  - [x] 14.2 Implement the settings module
    - Add `modules/settings/` with `GET/PUT /api/staff/settings` (default low-stock threshold for new products) and use it in product creation
    - _Requirements: 6.4, 20.1_

  - [x] 14.3 Implement the pure forecasting core
    - Add `modules/forecasting/model.py`: `forecast_series(units, stock, threshold)` with continuous monthly reindex, Baseline_Model (mean of last `min(3, n)`), Candidate_Model (NumPy `lstsq` with trend and seasonal dummies only when `n >= 24`), clamp at 0 and round to 2 decimals, backtest on last 2 months when `n >= 6`, MAE and RMSE, selection (candidate only when strictly lower MAE), short-history response, replenishment flag, constant methodology object; no clock, randomness or I/O
    - _Requirements: 27.1, 27.2, 27.3, 27.4, 27.5, 27.7, 27.8, 27.9, 27.12, 27.13_

  - [x] 14.4 Implement the forecasting service and router
    - Add `service.py` (reads `orders.api.monthly_units`, `inventory.api`, sets `synthetic` flag) and `GET /api/staff/forecast/{product_id}`; no history returns 422 `forecast_no_history`; core failure returns 500 `forecast_failed` with a safe message; register analytics, settings and forecasting routers in `main.py`
    - _Requirements: 27.1, 27.6, 27.7, 27.10, 27.11_

  - [x] 14.5 Write property test for analytics invariants
    - **Property 32: Analytics invariants**
    - **Validates: Requirements 19.2, 19.3, 26.1, 26.2, 26.7**

  - [x] 14.6 Write property test for analytics exclusions and rankings
    - **Property 33: Analytics exclusions and rankings**
    - **Validates: Requirements 19.3, 19.6, 26.3, 26.4, 26.6**

  - [x] 14.7 Write property test for forecast history construction
    - **Property 34: Forecast history construction**
    - **Validates: Requirements 27.1**

  - [x] 14.8 Write property test for forecast output shape and non-negativity
    - **Property 35: Forecast output shape and non-negativity**
    - **Validates: Requirements 27.2, 27.4, 27.12**

  - [x] 14.9 Write property test for backtest metrics and model selection
    - **Property 36: Backtest metrics and model selection**
    - **Validates: Requirements 27.3, 27.4, 27.5, 27.9**

  - [x] 14.10 Write property test for forecast determinism
    - **Property 37: Forecast determinism**
    - **Validates: Requirements 27.13**

  - [x] 14.11 Write property test for replenishment flag and synthetic marker
    - **Property 38: Replenishment flag and synthetic marker**
    - **Validates: Requirements 27.6, 27.7**

  - [x] 14.12 Write unit tests for analytics, settings and forecasting
    - Success and failure path for dashboard with empty data (all zero), range validation, forecast with short history, no history and a seasonal series
    - _Requirements: 19.9, 26.6, 27.4, 27.10, 31.1_

- [x] 15. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Flutter shell, theme and network layer
  - [x] 16.1 Update dependencies and create core utilities
    - Add `flutter_riverpod`, `go_router`, `flutter_secure_storage`, `fl_chart`, `image_picker` (pinned via `flutter pub add`) and dev `mocktail`, `glados` to `pubspec.yaml`; create `lib/core/money.dart` (`formatRm`, output identical to the old `money()`), `validators.dart` (name, email, Malaysian phone, postcode, address, 16 states, password, URL), `constants.dart` (states, categories, statuses), and `badge` label helper (`null`, decimal, `99+`)
    - _Requirements: 1.7, 2.3, 7.2, 7.4, 12.3, 17.9, 18.4, 18.5, 18.6_

  - [x] 16.2 Implement the Material 3 theme and shared widgets
    - Add `lib/app/theme.dart` (Primary #123D32, Secondary #87A999, Background #F8F5EE, Accent #E9C879, Text #26332E, white cards, 12-16 px radius, 4.5:1 contrast) and `lib/core/widgets/` (`LoadingView`, `ErrorView` with retry, `EmptyView` with one next-step action, `DemoLabel`, `AppIconButton` with required semantic label, `BadgeCount`, `AsyncValueView<T>`)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11_

  - [x] 16.3 Implement API configuration, client and token storage
    - Add `ApiConfigNotifier` (override over `--dart-define API_BASE_URL` over platform default `http://localhost:8000` or `http://10.0.2.2:8000`, validated override, clear to revert), `ApiClient` (Bearer token, 10 s reachability and 15 s request timeouts, error mapping to sealed `AppFailure`), and `TokenStore` (secure storage with `shared_preferences` fallback on web)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.5, 5.8_

  - [x] 16.4 Implement session, router and role-based shells
    - Add `sessionProvider` (`checking / signedOut / signedIn / serverUnreachable`, start-up validation with 10 s timeout, delete token on 401, keep it when unreachable), `routerProvider` (go_router, role redirect, `/login?from=` return, cancel returns to previous route), `RolePermissions` map, `customer_shell.dart` (Home, Shop, Favourites, Cart, Profile) and `staff_shell.dart` (Dashboard, Orders, Products, Production, More; Artisan_User sees Production only); feature route lists are composed here so feature tasks do not edit the router
    - _Requirements: 5.5, 5.6, 5.9, 5.10, 5.11, 6.10, 6.11, 18.1, 18.7, 18.8, 19.1_

  - [x] 16.5 Migrate the old `main.dart` stores
    - Replace `lib/main.dart` with a thin `ProviderScope` entry; add `LegacyLocalStore` / `GuestCartRepository` (same `shared_preferences` keys, qty clamp 1-20), `LocalFavouritesRepository`, `LegacyOrdersRepository` (old saved orders tracked through `/api/legacy/orders` and listed as legacy guest orders), and a product repository with server-first, bundled-JSON fallback accepting `priceSen` or `demoPriceSen`; move widget code into feature folders before changing behaviour
    - _Requirements: 1.1, 1.7, 10.10, 10.11, 11.12, 11.13_

  - [x] 16.6 Write property test for API base URL validation and precedence
    - **Property 5: API base URL validation and precedence**
    - **Validates: Requirements 2.2, 2.3, 2.5**

  - [x] 16.7 Write property test for role to navigation mapping
    - **Property 12: Role to navigation mapping**
    - **Validates: Requirements 6.10, 18.1, 19.1**

  - [x] 16.8 Write property test for delivery and field validators (Dart)
    - **Property 17: Delivery and field validators** (Dart side)
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.5, 12.3, 12.4, 16.1, 16.8**

  - [x] 16.9 Write property test for the badge label
    - **Property 31: Badge label**
    - **Validates: Requirements 17.9, 17.10, 18.4, 18.5, 18.6**

  - [x] 16.10 Write Flutter unit and widget tests for the shell
    - Money formatting, form validators, error state display, empty state display, loading indicator removal, semantic labels on icon buttons
    - _Requirements: 3.3, 3.4, 3.5, 3.11, 31.2_

- [x] 17. Customer features
  - [x] 17.1 Implement authentication screens and session actions
    - Add `features/auth/` login and register screens with Demo_Label on login, fictional-data notice visible without scrolling on registration and at first launch, field errors from 422, 429 lockout message with remaining seconds, logout; on first sign-in trigger favourites upload and cart merge
    - _Requirements: 3.7, 4.1, 4.4, 5.1, 5.2, 5.3, 5.9, 10.10, 11.12, 33.6_

  - [x] 17.2 Implement Home, Shop and product detail
    - Add `features/home/` (branding, banner, collections, categories, best sellers, new arrivals, recommendations, story, search with whitespace rejection and focus kept, independent section loading with retry) and `features/catalogue/` (search, category filter, price sort, pagination, product detail with stock status text, variations, public artisan name, disabled add-to-cart when out of stock, Demo_Label next to demo items)
    - _Requirements: 3.9, 8.1, 8.6, 8.7, 8.8, 8.9, 9.10, 9.11, 9.12_

  - [x] 17.3 Implement favourites
    - Add `features/favourites/` with `favouritesProvider` (server list when signed in, local list for guests, first-sign-in merge that clears the local copy only after confirmed upload and retries on failure), error and retry states
    - _Requirements: 10.1, 10.3, 10.7, 10.8, 10.10, 10.11, 18.7_

  - [x] 17.4 Implement the cart
    - Add `features/cart/` with `cartProvider` (server cart when signed in, guest cart otherwise), unavailable-line flags, 409 stock messages, 99+ badge via `cartBadgeProvider`, empty state, and merge result showing items that were not merged
    - _Requirements: 11.1, 11.2, 11.3, 11.6, 11.7, 11.8, 11.12, 11.13, 18.4, 18.5, 18.6_

  - [x] 17.5 Implement checkout, payment and confirmation
    - Add `features/checkout/` four-step flow (`checkoutFlowProvider`, idempotency key once per attempt, form values kept on error, validation with per-field messages) and `features/payment/` (method choice, simulated outcome choice, no real card input, demo-only card field cleared in `dispose`, Demo_Label on payment and confirmation screens, could-not-process error leaving order and stock unchanged, retry of `payment_failed` orders)
    - _Requirements: 3.8, 12.1, 12.3, 12.4, 12.8, 13.1, 13.2, 13.8, 13.9, 13.10, 13.11, 13.13_

  - [x] 17.6 Implement orders and tracking
    - Add `features/orders/` My Orders (paging, last data kept on refresh failure, legacy guest orders section), order detail with status timeline (Placed, Confirmed, Preparing, Shipped, Delivered; terminal cancelled or payment-failed state), shipping reference and separate read-only production label
    - _Requirements: 15.1, 15.2, 15.3, 15.6, 15.7, 15.8, 15.9, 15.10_

  - [x] 17.7 Implement custom orders
    - Add `features/custom_orders/` request form (product type, description, quantity, preferred date, up to 5 images via `image_picker` with client-side type and size checks), list with status, detail with quoted price or rejection reason
    - _Requirements: 16.1, 16.2, 16.3, 16.5, 16.8_

  - [x] 17.8 Implement notifications, profile, addresses, About and connection settings
    - Add `features/notifications/` (list, mark read, mark all, `99+` unread badge), `features/profile/` (profile edit, address book with default, links to My Orders, Custom Orders, Notifications, About, logout, error and retry), `features/about/` (Demo_Label visible without scrolling) and `features/settings/` connection screen (validated URL save and clear, unreachable error showing the URL in use with retry)
    - _Requirements: 2.3, 2.4, 2.5, 2.6, 3.7, 7.1, 7.2, 7.4, 7.6, 7.9, 7.10, 17.6, 17.7, 17.9, 17.10_

  - [x] 17.9 Write property test for stock label and timeline rendering
    - **Property 47: Stock status text and timeline rendering**
    - **Validates: Requirements 9.11, 15.6, 15.7**

  - [x] 17.10 Write Flutter widget tests for customer features
    - Login form, cart state, empty state with next-step action, error state with retry, role-based navigation, Home search whitespace rejection
    - _Requirements: 8.7, 11.8, 18.1, 31.2_

- [x] 18. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 19. Seller, admin and artisan features
  - [x] 19.1 Implement the dashboard and analytics screens
    - Add `features/admin/dashboard/` and `features/admin/analytics/`: KPI cards (revenue, orders, pending, AOV, low stock, open production, shipped), `fl_chart` charts with axis titles and `Semantics` text values, date range pickers with range errors, zero-state KPIs (RM 0.00) and chart empty states, Demo_Label
    - _Requirements: 3.9, 19.1, 19.2, 19.3, 19.4, 19.5, 19.7, 19.8, 19.9, 26.1, 26.2, 26.3, 26.4, 26.5_

  - [x] 19.2 Implement staff order management
    - Add `features/admin/orders/`: list with status filter, search and paging, detail, status change with shipping reference and cancel reason prompts, invalid-transition messages, legacy orders visible
    - _Requirements: 22.1, 22.2, 22.3, 22.4, 22.5, 22.6, 22.7, 22.8, 22.12, 22.13_

  - [x] 19.3 Implement product and inventory management
    - Add `features/admin/products/` (list, create and edit form retaining values on rejection, image upload, activate or deactivate, delete with 409 guidance) and `features/admin/inventory/` (stock list, low-stock alerts and count, adjust with reason, threshold edit, adjustment history)
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.8, 20.9, 20.11, 20.12, 21.1, 21.2, 21.3, 21.5, 21.7, 21.9_

  - [x] 19.4 Implement artisan and production screens
    - Add `features/admin/artisans/` (list, form, private contact for staff only, unavailable warning) and `features/admin/production/` (list and board views, filters with clear-filters empty state, assign form, status transitions, progress update, overdue indicator; Artisan_User sees only assigned jobs)
    - _Requirements: 23.1, 23.3, 23.4, 23.6, 24.2, 24.3, 24.4, 24.6, 24.7, 24.8, 24.12, 24.13_

  - [x] 19.5 Implement custom-order management, forecasting, notifications and settings screens
    - Add staff custom-order list and actions (accept with price, reject with reason, assign artisan, status), `features/admin/forecasting/` (history and forecast chart, baseline vs candidate, MAE and RMSE or "insufficient history", replenishment flag, methodology text, Synthetic_Data and Demo_Label notices), staff notifications and settings (default threshold)
    - _Requirements: 3.9, 17.6, 25.1, 25.2, 25.3, 25.4, 25.5, 25.6, 25.7, 27.2, 27.3, 27.4, 27.5, 27.6, 27.7, 27.8, 27.10_

  - [x] 19.6 Write Flutter widget tests for staff features
    - Dashboard zero state, role-filtered staff navigation including Artisan_User, order status change prompts, production empty state
    - _Requirements: 19.9, 24.13, 31.2_

- [x] 20. Seed script
  - [x] 20.1 Implement `backend/seed.py`
    - Single transaction with rollback and non-zero exit on any error; exit 2 with `Seeded data already exists` when demo rows exist; create at least 15 products (4 from `assets/products.json` with ids preserved, at least 2 per category, at least 2 at or below threshold, at least 5 above), 3 customers, 1 seller, 1 admin, 1 artisan user, 4 artisans, at least one order per Fulfilment_Status, one production job per Production_Status, a custom order, 3 notifications and 12 consecutive months of synthetic sales (`source='synthetic'`, `random.Random(20250101)`); opening stock without adjustment rows; passwords from `DEMO_*_PASSWORD` env vars with documented defaults; all records `is_demo = 1`
    - `--reset` requires the exact word `RESET-DEMO` (otherwise exit 3, `Reset cancelled`), deletes only demo rows children-first, excludes `source='legacy'`, then re-seeds
    - _Requirements: 29.1, 29.2, 29.3, 29.4, 29.5, 29.6, 29.7, 29.8, 29.9, 29.10, 29.11, 29.12_

  - [x] 20.2 Write property test and unit tests for the seed script
    - **Property 53: Seed reset confirmation**
    - Unit tests for counts, idempotent refusal, rollback on injected failure and preserved legacy orders
    - **Validates: Requirements 29.7, 29.9, 29.12**

- [x] 21. Documentation
  - [x] 21.1 Write the README
    - Ordered Windows and VS Code setup (prerequisites, venv, `pip install -r backend/requirements.txt`, `flutter pub get`, migrate, seed), run commands for web, Android emulator (`10.0.2.2`) and physical device with `API_BASE_URL`, APK build steps and location, demo credentials per Role labelled demo-only, feature checklist with exactly one row per Requirement 1 to 33 (`complete`, `partial`, `not done` with reasons), limitations (simulated payments, no courier, no e-mail, no push, synthetic forecasting data, SQLite scale), commercial-use changes (payment gateway, courier APIs, production database, secrets management, image rights, PDPA, HTTPS, security review), and the independent-prototype disclaimer
    - _Requirements: 3.7, 29.10, 31.7, 32.1, 32.2, 32.3, 32.4, 32.5, 32.6, 32.7, 32.8, 32.10_

- [x] 22. Integration and end-to-end tests
  - [x] 22.1 Add the module architecture test
    - Parse each module's `repository.py` for table names after `FROM|JOIN|INTO|UPDATE|DELETE FROM` and fail on tables outside the module's row in the ownership table; fail when a module imports another module's `repository`, `service` or `schemas` instead of `api`
    - _Requirements: 1.6, 28.7_

  - [x] 22.2 Write property test for the access control matrix
    - **Property 9: Access control matrix**
    - **Validates: Requirements 6.1, 6.2, 6.4, 6.5, 6.7, 6.8, 10.6, 20.10, 23.8, 33.1**

  - [x] 22.3 Write property test for ownership isolation
    - **Property 10: Ownership isolation**
    - **Validates: Requirements 6.3, 6.9, 7.8, 15.1, 15.4, 16.5, 17.6, 17.8**

  - [x] 22.4 Write the end-to-end scenario test through the HTTP API
    - One test executing steps 1 to 7: customer login, browse, add to cart, checkout with successful demo payment (one order, cart empty, stock decreased), staff sees the same order, staff confirms and assigns a job (one job, visible to the Artisan_User), progress update visible on customer tracking, `shipped` with shipping reference, dashboard KPIs and best sellers increased by the order contribution; fail with the failed step name and run no later steps
    - _Requirements: 30.1, 30.2, 30.3, 30.4, 30.5, 30.6, 30.7, 30.8, 30.9_

  - [x] 22.5 Write contract tests for OpenAPI and money fields
    - `/docs` and `/openapi.json` return 200, every public endpoint is described, and every response model field ending in `Sen` is `int`
    - _Requirements: 1.11, 28.5, 31.1_

  - [x] 22.6 Run all suites and record real results in the README
    - Run `pytest` and `flutter test`; add the exact commands, passed and failed counts and the date to the README, reporting only runs actually executed
    - _Requirements: 31.1, 31.2, 31.3, 31.4, 31.7_

- [x] 23. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (Hypothesis on the backend, glados on Flutter) and run at least 100 generated inputs each
- Unit tests validate specific examples and edge cases
- Backend tests use an isolated temporary database that is deleted at teardown

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "1.5", "1.6", "1.7", "1.8", "1.9"] },
    { "id": 3, "tasks": ["3.1"] },
    { "id": 4, "tasks": ["3.2"] },
    { "id": 5, "tasks": ["3.3"] },
    { "id": 6, "tasks": ["3.4"] },
    { "id": 7, "tasks": ["3.5", "3.6", "3.7", "3.8", "3.9"] },
    { "id": 8, "tasks": ["5.1", "5.2"] },
    { "id": 9, "tasks": ["5.3"] },
    { "id": 10, "tasks": ["5.4", "5.5"] },
    { "id": 11, "tasks": ["5.6", "5.7", "5.8", "5.9", "5.10"] },
    { "id": 12, "tasks": ["7.1", "7.2"] },
    { "id": 13, "tasks": ["7.3", "7.4"] },
    { "id": 14, "tasks": ["7.5"] },
    { "id": 15, "tasks": ["7.6", "7.7", "7.8"] },
    { "id": 16, "tasks": ["7.9", "7.10", "7.11", "7.12", "7.13", "7.14", "7.15", "7.16", "7.17", "7.18", "7.19", "7.20", "7.21", "7.22", "7.23", "7.24", "7.25"] },
    { "id": 17, "tasks": ["9.1"] },
    { "id": 18, "tasks": ["9.2", "9.3"] },
    { "id": 19, "tasks": ["11.1"] },
    { "id": 20, "tasks": ["11.2"] },
    { "id": 21, "tasks": ["11.3"] },
    { "id": 22, "tasks": ["11.4"] },
    { "id": 23, "tasks": ["11.5", "11.6", "11.7", "11.8", "11.9", "11.10"] },
    { "id": 24, "tasks": ["13.1"] },
    { "id": 25, "tasks": ["13.2", "13.3", "13.4"] },
    { "id": 26, "tasks": ["14.1", "14.2", "14.3"] },
    { "id": 27, "tasks": ["14.4"] },
    { "id": 28, "tasks": ["14.5", "14.6", "14.7", "14.8", "14.9", "14.10", "14.11", "14.12"] },
    { "id": 29, "tasks": ["16.1"] },
    { "id": 30, "tasks": ["16.2", "16.3"] },
    { "id": 31, "tasks": ["16.4", "16.5"] },
    { "id": 32, "tasks": ["16.6", "16.7", "16.8", "16.9", "16.10"] },
    { "id": 33, "tasks": ["17.1", "17.2", "17.3"] },
    { "id": 34, "tasks": ["17.4", "17.5", "17.6"] },
    { "id": 35, "tasks": ["17.7", "17.8"] },
    { "id": 36, "tasks": ["17.9", "17.10"] },
    { "id": 37, "tasks": ["19.1", "19.2", "19.3"] },
    { "id": 38, "tasks": ["19.4", "19.5"] },
    { "id": 39, "tasks": ["19.6"] },
    { "id": 40, "tasks": ["20.1"] },
    { "id": 41, "tasks": ["20.2"] },
    { "id": 42, "tasks": ["21.1"] },
    { "id": 43, "tasks": ["22.1", "22.2", "22.3", "22.4", "22.5"] },
    { "id": 44, "tasks": ["22.6"] }
  ]
}
```
