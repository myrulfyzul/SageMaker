-- 0009 custom orders.
CREATE TABLE custom_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  product_type TEXT NOT NULL CHECK (length(product_type) BETWEEN 1 AND 100),
  description TEXT NOT NULL CHECK (length(description) BETWEEN 10 AND 2000),
  quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 500),
  preferred_date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'submitted'
    CHECK (status IN ('submitted','accepted','rejected','in_progress','completed')),
  estimated_price_sen INTEGER CHECK (estimated_price_sen BETWEEN 1 AND 99999999),
  reject_reason TEXT, artisan_id INTEGER, production_job_id INTEGER,
  is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE custom_order_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  custom_order_id INTEGER NOT NULL REFERENCES custom_orders(id) ON DELETE CASCADE,
  filename TEXT NOT NULL UNIQUE, content_type TEXT NOT NULL, size_bytes INTEGER NOT NULL
);