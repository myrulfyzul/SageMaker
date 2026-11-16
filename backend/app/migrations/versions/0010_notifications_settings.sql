-- 0010 notifications and app settings.
CREATE TABLE notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type TEXT NOT NULL CHECK (type IN ('order','custom_order','low_stock','production','system')),
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 100),
  body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 500),
  related_type TEXT, related_id TEXT,
  is_read INTEGER NOT NULL DEFAULT 0, is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);