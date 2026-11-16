-- 0002 users, sessions, login attempts, addresses.
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
  email TEXT NOT NULL, email_lower TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  phone TEXT,
  role TEXT NOT NULL CHECK (role IN ('customer','seller','admin','artisan')),
  is_active INTEGER NOT NULL DEFAULT 1, is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT
);
CREATE TABLE login_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email_lower TEXT NOT NULL, succeeded INTEGER NOT NULL, attempted_at TEXT NOT NULL
);
CREATE TABLE addresses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  recipient_name TEXT NOT NULL, phone TEXT NOT NULL,
  line1 TEXT NOT NULL, line2 TEXT, postcode TEXT NOT NULL CHECK (length(postcode) = 5),
  city TEXT NOT NULL, state TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_addresses_default ON addresses(user_id) WHERE is_default = 1;