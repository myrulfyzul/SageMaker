-- 0004 inventory tables.
CREATE TABLE stock_levels (
  sku_key TEXT PRIMARY KEY,                -- product_id or product_id || '#' || variation_id
  product_id TEXT NOT NULL, variation_id INTEGER,
  quantity INTEGER NOT NULL CHECK (quantity >= 0),
  opening_quantity INTEGER NOT NULL CHECK (opening_quantity >= 0)
);
CREATE TABLE inventory_settings (
  product_id TEXT PRIMARY KEY,
  low_stock_threshold INTEGER NOT NULL DEFAULT 5 CHECK (low_stock_threshold BETWEEN 0 AND 999999999)
);
CREATE TABLE stock_adjustments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sku_key TEXT NOT NULL, product_id TEXT NOT NULL,
  delta INTEGER NOT NULL CHECK (delta <> 0),
  reason TEXT NOT NULL CHECK (length(reason) BETWEEN 1 AND 255),
  actor_user_id INTEGER, order_id TEXT,
  created_at TEXT NOT NULL
);