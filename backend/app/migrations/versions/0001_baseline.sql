-- 0001 baseline: identical to the legacy definition in backend/server.py.
-- No-op on an existing prototype database.
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY, checkout_id TEXT NOT NULL UNIQUE,
  secret_token TEXT NOT NULL, customer_name TEXT NOT NULL,
  email TEXT NOT NULL, phone TEXT NOT NULL, delivery_address TEXT NOT NULL,
  payment_method TEXT NOT NULL, payment_status TEXT NOT NULL,
  status TEXT NOT NULL, shipping_fee_sen INTEGER NOT NULL,
  total_sen INTEGER NOT NULL, items_json TEXT NOT NULL,
  tracking_number TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);