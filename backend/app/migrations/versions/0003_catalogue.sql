-- 0003 categories (5 seed rows), products, variations, images.
CREATE TABLE categories (id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL UNIQUE, sort_order INTEGER NOT NULL);
INSERT INTO categories (id, slug, name, sort_order) VALUES (1, 'tote-bags', 'Tote bags', 1);
INSERT INTO categories (id, slug, name, sort_order) VALUES (2, 'fabric-books', 'Fabric books', 2);
INSERT INTO categories (id, slug, name, sort_order) VALUES (3, 'toys', 'Toys', 3);
INSERT INTO categories (id, slug, name, sort_order) VALUES (4, 'gifts', 'Gifts', 4);
INSERT INTO categories (id, slug, name, sort_order) VALUES (5, 'accessories', 'Accessories', 5);
CREATE TABLE products (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
  description TEXT NOT NULL DEFAULT '' CHECK (length(description) <= 2000),
  category_id INTEGER NOT NULL REFERENCES categories(id),
  price_sen INTEGER NOT NULL CHECK (price_sen BETWEEN 1 AND 99999999),
  artisan_id INTEGER,                      -- logical link to artisans.id, checked by the service
  made_to_order INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  legacy_image_url TEXT, legacy_product_url TEXT,
  is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE product_variations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  label TEXT NOT NULL, price_delta_sen INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE product_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  filename TEXT, external_url TEXT, sort_order INTEGER NOT NULL DEFAULT 0, is_demo INTEGER NOT NULL DEFAULT 0
);