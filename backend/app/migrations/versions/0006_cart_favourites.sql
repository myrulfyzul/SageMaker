-- 0006 cart and favourites.
CREATE TABLE cart_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  product_id TEXT NOT NULL, variation_id INTEGER, sku_key TEXT NOT NULL,
  quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 20),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE (user_id, sku_key)
);
CREATE TABLE favourites (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  product_id TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, product_id)
);