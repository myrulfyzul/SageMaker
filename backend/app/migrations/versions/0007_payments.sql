-- 0007 simulated payments.
CREATE TABLE payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL REFERENCES orders(id),
  method TEXT NOT NULL CHECK (method IN ('card','fpx','ewallet','cod')),
  outcome TEXT NOT NULL CHECK (outcome IN ('success','failed','cancelled','pending_cod')),
  amount_sen INTEGER NOT NULL CHECK (amount_sen > 0),
  is_demo INTEGER NOT NULL DEFAULT 1 CHECK (is_demo = 1),
  created_at TEXT NOT NULL
);