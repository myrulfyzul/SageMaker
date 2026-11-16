-- Hosted-gateway payments (Stripe sandbox). A session is created when the customer starts paying; the order
-- itself is only created once the gateway confirms the money, so an unpaid attempt never holds stock.
CREATE TABLE payment_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    idempotency_key TEXT NOT NULL,
    gateway TEXT NOT NULL,
    gateway_session_id TEXT UNIQUE,
    checkout_url TEXT,
    method TEXT NOT NULL,
    provider TEXT,
    amount_sen INTEGER NOT NULL CHECK (amount_sen > 0),
    delivery_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'cancelled', 'expired', 'failed', 'refunded')),
    order_id TEXT,
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, idempotency_key)
);

CREATE INDEX idx_payment_sessions_user ON payment_sessions (user_id, created_at);

-- Gateway reference (Stripe PaymentIntent id) of the charge, for support and refunds.
ALTER TABLE payments ADD COLUMN reference TEXT;
