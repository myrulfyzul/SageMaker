-- 0008 artisans and production.
CREATE TABLE artisans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER UNIQUE REFERENCES users(id),
  name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
  specialisation TEXT NOT NULL CHECK (length(specialisation) BETWEEN 1 AND 100),
  availability TEXT NOT NULL CHECK (availability IN ('available','busy','unavailable')),
  story TEXT NOT NULL DEFAULT '' CHECK (length(story) <= 2000),
  private_phone TEXT, private_email TEXT, private_address TEXT,
  is_active INTEGER NOT NULL DEFAULT 1, is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE production_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT, order_line_id INTEGER, custom_order_id INTEGER,
  product_id TEXT, artisan_id INTEGER,
  quantity INTEGER CHECK (quantity BETWEEN 1 AND 999999),
  deadline TEXT, priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low','normal','high','urgent')),
  status TEXT NOT NULL DEFAULT 'order_confirmed'
    CHECK (status IN ('order_confirmed','production_assigned','in_production','quality_checking','completed','ready_for_fulfilment')),
  progress_percent INTEGER NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
  notes TEXT NOT NULL DEFAULT '' CHECK (length(notes) <= 1000),
  is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE production_progress (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL REFERENCES production_jobs(id) ON DELETE CASCADE,
  percent INTEGER NOT NULL CHECK (percent BETWEEN 0 AND 100),
  note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 500),
  actor_user_id INTEGER, created_at TEXT NOT NULL
);