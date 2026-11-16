-- Bank, e-wallet or QR scheme chosen at payment (e.g. maybank2u, tng, duitnow). Nullable: COD, card and
-- orders placed before this migration have none. Add-only, so existing rows keep their values.
ALTER TABLE orders ADD COLUMN payment_provider TEXT;
ALTER TABLE payments ADD COLUMN provider TEXT;
