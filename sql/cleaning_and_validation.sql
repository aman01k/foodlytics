-- Data-quality checks. Each query is named and returns ONE row:
--   (check_name, failures, detail). failures = 0 means pass.
-- Executed by src/validate_data.py and tests/test_data_quality.py.

-- name: pk_orders_unique
SELECT 'pk_orders_unique' AS check_name, COUNT(*) - COUNT(DISTINCT order_id) AS failures, 'duplicate order_id' AS detail FROM clean.orders;
-- name: pk_items_unique
SELECT 'pk_items_unique', COUNT(*) - COUNT(DISTINCT (order_id, order_item_id)), 'duplicate (order_id, order_item_id)' FROM clean.order_items;
-- name: pk_payments_unique
SELECT 'pk_payments_unique', COUNT(*) - COUNT(DISTINCT (order_id, payment_sequential)), 'duplicate payment pk' FROM clean.order_payments;
-- name: pk_reviews_one_per_order
SELECT 'pk_reviews_one_per_order', COUNT(*) - COUNT(DISTINCT order_id), 'orders with >1 kept review' FROM clean.order_reviews;
-- name: fk_orders_customers
SELECT 'fk_orders_customers', COUNT(*), 'orders without customer' FROM clean.orders o LEFT JOIN clean.customers c USING (customer_id) WHERE c.customer_id IS NULL;
-- name: fk_items_orders
SELECT 'fk_items_orders', COUNT(*), 'items without order' FROM clean.order_items i LEFT JOIN clean.orders o USING (order_id) WHERE o.order_id IS NULL;
-- name: fk_items_products
SELECT 'fk_items_products', COUNT(*), 'items without product' FROM clean.order_items i LEFT JOIN clean.products p USING (product_id) WHERE p.product_id IS NULL;
-- name: fk_items_sellers
SELECT 'fk_items_sellers', COUNT(*), 'items without seller' FROM clean.order_items i LEFT JOIN clean.sellers s USING (seller_id) WHERE s.seller_id IS NULL;
-- name: fk_products_categories
SELECT 'fk_products_categories', COUNT(*), 'products with untranslated category' FROM clean.products p LEFT JOIN clean.product_categories c USING (product_category_name) WHERE c.product_category_name IS NULL;
-- name: critical_nulls_orders
SELECT 'critical_nulls_orders', COUNT(*), 'orders missing id/customer/status/purchase ts' FROM clean.orders WHERE order_id IS NULL OR customer_id IS NULL OR order_status IS NULL OR order_purchase_timestamp IS NULL;
-- name: invalid_prices
SELECT 'invalid_prices', COUNT(*), 'price<=0 or freight<0' FROM clean.order_items WHERE price <= 0 OR freight_value < 0;
-- name: delivered_before_purchase
SELECT 'delivered_before_purchase', COUNT(*), 'delivered timestamp precedes purchase' FROM clean.orders WHERE order_delivered_customer_date < order_purchase_timestamp;
-- name: raw_clean_row_reconciliation
SELECT 'raw_clean_row_reconciliation',
       (SELECT COUNT(*) FROM raw.orders)      - (SELECT COUNT(*) FROM clean.orders)
     + (SELECT COUNT(*) FROM raw.order_items) - (SELECT COUNT(*) FROM clean.order_items)
     + (SELECT COUNT(*) FROM raw.order_payments) - (SELECT COUNT(*) FROM clean.order_payments)
     + (SELECT COUNT(*) FROM raw.customers)   - (SELECT COUNT(*) FROM clean.customers),
       'row-count difference raw vs clean for orders/items/payments/customers (must be 0: nothing dropped)';
-- name: fct_orders_no_fanout
SELECT 'fct_orders_no_fanout', (SELECT COUNT(*) FROM analytics.fct_orders) - (SELECT COUNT(*) FROM clean.orders), 'order fact must have exactly one row per order';
-- name: gmv_reconciles_to_items
SELECT 'gmv_reconciles_to_items',
       (ABS((SELECT SUM(gmv) FROM analytics.fct_orders) - (SELECT SUM(price) FROM clean.order_items)) > 0.01)::int,
       'SUM(order gmv) must equal SUM(item price)';
-- name: payments_reconcile_to_table
SELECT 'payments_reconcile_to_table',
       (ABS((SELECT SUM(payment_value) FROM analytics.fct_orders) - (SELECT SUM(payment_value) FROM clean.order_payments)) > 0.01)::int,
       'SUM(order payment_value) must equal SUM(payments)';
-- name: payment_vs_items_mismatch_share
-- Informational: share of orders whose payments differ from items+freight by > R$1
-- (installment interest, vouchers). Not a failure; threshold 1%.
SELECT 'payment_vs_items_mismatch_share',
       (AVG((ABS(payment_value - order_value) > 1)::int) > 0.01)::int,
       'share of orders where |payment - (price+freight)| > R$1: ' || ROUND(100 * AVG((ABS(payment_value - order_value) > 1)::int), 3) || '%'
FROM analytics.fct_orders WHERE payment_value IS NOT NULL AND order_value IS NOT NULL;
-- name: customers_universe_matches
SELECT 'customers_universe_matches',
       (SELECT COUNT(*) FROM analytics.dim_customers) -
       (SELECT COUNT(DISTINCT customer_unique_id) FROM analytics.fct_orders f, analytics.params p WHERE f.is_valid AND f.purchase_ts < p.window_end),
       'dim_customers must contain each customer with a valid order exactly once';
-- name: cohort_sizes_sum
SELECT 'cohort_sizes_sum',
       (SELECT SUM(cohort_size) FROM (SELECT DISTINCT cohort_month, cohort_size FROM analytics.v_cohort_retention) x) -
       (SELECT COUNT(*) FROM analytics.dim_customers c, analytics.params p WHERE c.cohort_month >= p.window_start),
       'cohort sizes must sum to customers acquired in window';
-- name: cohort_month0_is_100pct
SELECT 'cohort_month0_is_100pct', COUNT(*), 'every cohort must be 100% active in month 0'
FROM analytics.v_cohort_retention WHERE months_since_first = 0 AND retention_rate <> 1;
