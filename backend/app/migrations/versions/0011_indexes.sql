-- 0011 indexes.
CREATE INDEX ix_orders_user ON orders(user_id, created_at DESC);
CREATE INDEX ix_orders_status ON orders(status, created_at DESC);
CREATE INDEX ix_order_lines_order ON order_lines(order_id);
CREATE INDEX ix_order_lines_product ON order_lines(product_id);
CREATE INDEX ix_products_active_cat ON products(is_active, category_id, price_sen);
CREATE INDEX ix_notifications_user ON notifications(user_id, is_read, created_at DESC);
CREATE INDEX ix_login_attempts ON login_attempts(email_lower, attempted_at);
CREATE INDEX ix_sessions_user ON sessions(user_id);
CREATE INDEX ix_prod_jobs_status ON production_jobs(status, artisan_id, priority);
CREATE INDEX ix_stock_adj_product ON stock_adjustments(product_id, created_at DESC);