-- 0005 orders extension (add-only; legacy rows are never updated or deleted).
ALTER TABLE orders ADD COLUMN user_id INTEGER;                       -- NULL for legacy/guest
ALTER TABLE orders ADD COLUMN source TEXT NOT NULL DEFAULT 'legacy'; -- legacy | app | synthetic
ALTER TABLE orders ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 1;
ALTER TABLE orders ADD COLUMN delivery_postcode TEXT;
ALTER TABLE orders ADD COLUMN delivery_state TEXT;
ALTER TABLE orders ADD COLUMN delivery_notes TEXT;
ALTER TABLE orders ADD COLUMN subtotal_sen INTEGER;
ALTER TABLE orders ADD COLUMN shipping_reference TEXT;               -- mirrors legacy tracking_number
ALTER TABLE orders ADD COLUMN cancel_reason TEXT;
ALTER TABLE orders ADD COLUMN stock_restored INTEGER NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN stock_restored_at TEXT;
CREATE TABLE order_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL REFERENCES orders(id),
  product_id TEXT NOT NULL, variation_id INTEGER, sku_key TEXT NOT NULL,
  name TEXT NOT NULL, variation_label TEXT,
  unit_price_sen INTEGER NOT NULL CHECK (unit_price_sen > 0),
  quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 20),
  line_total_sen INTEGER NOT NULL
);
CREATE TABLE order_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL REFERENCES orders(id),
  previous_status TEXT, new_status TEXT NOT NULL,
  actor_user_id INTEGER, reason TEXT, created_at TEXT NOT NULL
);
CREATE TRIGGER order_history_no_update BEFORE UPDATE ON order_history BEGIN SELECT RAISE(ABORT, 'order_history is append-only'); END;
CREATE TRIGGER order_history_no_delete BEFORE DELETE ON order_history BEGIN SELECT RAISE(ABORT, 'order_history is append-only'); END;