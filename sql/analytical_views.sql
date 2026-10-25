-- =====================================================================
-- Foodlytics analytics layer. Rebuilt from scratch on every load.
-- Grain discipline: order_items (item grain) and order_payments (payment
-- grain) are ALWAYS aggregated to order grain in separate CTEs before they
-- meet, so no order value is ever multiplied by a join fan-out.
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS analytics;

-- ---------------------------------------------------------------------
-- 0. Parameters shared by every view (single source of truth)
-- ---------------------------------------------------------------------
CREATE TABLE analytics.params AS
SELECT DATE '2017-01-01' AS window_start,   -- 2016 = platform ramp-up (329 orders, gaps)
       DATE '2018-09-01' AS window_end,     -- exclusive; Sep/Oct 2018 = 20 orders, data cut-off
       DATE '2018-09-01' AS snapshot_date,  -- "today" for recency
       180               AS inactive_days,  -- potentially-inactive threshold (not a churn label)
       0.80              AS high_value_pctl;

-- ---------------------------------------------------------------------
-- 1. Order fact: one row per order
-- ---------------------------------------------------------------------
CREATE TABLE analytics.fct_orders AS
WITH items AS (
    SELECT order_id,
           COUNT(*)                   AS n_items,
           COUNT(DISTINCT product_id) AS n_products,
           COUNT(DISTINCT seller_id)  AS n_sellers,
           SUM(price)                 AS gmv,
           SUM(freight_value)         AS freight
    FROM clean.order_items
    GROUP BY order_id
), pay AS (
    SELECT order_id,
           SUM(payment_value)                                          AS payment_value,
           COUNT(*)                                                    AS n_payments,
           MAX(payment_installments)                                   AS max_installments,
           BOOL_OR(payment_type = 'voucher')                           AS used_voucher,
           (ARRAY_AGG(payment_type ORDER BY payment_value DESC, payment_sequential))[1] AS primary_payment_type
    FROM clean.order_payments
    GROUP BY order_id
), base AS (
    SELECT o.order_id,
           o.customer_id,
           c.customer_unique_id,
           c.customer_state,
           o.order_status,
           o.order_purchase_timestamp                                  AS purchase_ts,
           DATE_TRUNC('month', o.order_purchase_timestamp)::date       AS purchase_month,
           o.order_status = 'delivered'                                AS is_delivered,
           o.order_status = 'canceled'                                 AS is_canceled,
           o.order_status = 'unavailable'                              AS is_unavailable,
           i.order_id IS NOT NULL                                      AS has_items,
           -- valid order = a real purchase: not canceled/unavailable and has line items
           (o.order_status NOT IN ('canceled', 'unavailable') AND i.order_id IS NOT NULL) AS is_valid,
           COALESCE(i.n_items, 0)                                      AS n_items,
           i.n_products, i.n_sellers,
           i.gmv,
           i.freight,
           i.gmv + i.freight                                           AS order_value,
           p.payment_value,
           p.n_payments, p.max_installments, p.used_voucher, p.primary_payment_type,
           -- time metrics (NULL when the underlying timestamps are missing/invalid)
           CASE WHEN o.order_approved_at IS NOT NULL
                THEN EXTRACT(EPOCH FROM o.order_approved_at - o.order_purchase_timestamp) / 3600 END
                                                                       AS approval_hours,
           CASE WHEN o.order_delivered_carrier_date >= o.order_purchase_timestamp
                THEN EXTRACT(EPOCH FROM o.order_delivered_carrier_date - o.order_purchase_timestamp) / 86400 END
                                                                       AS handover_days,
           CASE WHEN o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
                THEN EXTRACT(EPOCH FROM o.order_delivered_customer_date - o.order_purchase_timestamp) / 86400 END
                                                                       AS delivery_days,
           CASE WHEN o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
                THEN o.order_delivered_customer_date::date <= o.order_estimated_delivery_date::date END
                                                                       AS is_on_time,
           CASE WHEN o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
                THEN o.order_delivered_customer_date::date - o.order_estimated_delivery_date::date END
                                                                       AS days_vs_estimate,   -- >0 = late
           EXTRACT(EPOCH FROM o.order_estimated_delivery_date - o.order_purchase_timestamp) / 86400
                                                                       AS promised_days,
           o.has_timestamp_anomaly,
           r.review_score
    FROM clean.orders o
    JOIN clean.customers c USING (customer_id)
    LEFT JOIN items i USING (order_id)
    LEFT JOIN pay   p USING (order_id)
    LEFT JOIN clean.order_reviews r USING (order_id)
)
SELECT b.*,
       b.purchase_ts >= pr.window_start AND b.purchase_ts < pr.window_end AS in_window,
       -- sequence of this order among the customer's valid orders up to window_end
       CASE WHEN b.is_valid AND b.purchase_ts < pr.window_end THEN
            ROW_NUMBER() OVER (PARTITION BY b.customer_unique_id,
                                            (b.is_valid AND b.purchase_ts < pr.window_end)
                               ORDER BY b.purchase_ts, b.order_id) END AS valid_order_seq
FROM base b CROSS JOIN analytics.params pr;

ALTER TABLE analytics.fct_orders ADD PRIMARY KEY (order_id);
CREATE INDEX ON analytics.fct_orders (customer_unique_id);
CREATE INDEX ON analytics.fct_orders (purchase_month);

-- ---------------------------------------------------------------------
-- 2. Item fact (item grain) with category + order context
-- ---------------------------------------------------------------------
CREATE VIEW analytics.fct_order_items AS
SELECT i.order_id, i.order_item_id, i.product_id, i.seller_id, i.price, i.freight_value,
       p.product_category_name,
       pc.product_category_name_english AS category,
       f.order_status, f.purchase_month, f.purchase_ts, f.in_window, f.is_valid,
       f.is_delivered, f.is_canceled, f.customer_unique_id, f.customer_state,
       f.delivery_days, f.is_on_time, f.days_vs_estimate, f.review_score
FROM clean.order_items i
JOIN clean.products p            USING (product_id)
JOIN clean.product_categories pc USING (product_category_name)
JOIN analytics.fct_orders f      USING (order_id);

-- ---------------------------------------------------------------------
-- 3. Customer dimension: one row per customer_unique_id with >=1 valid
--    order before window_end. Frequency = distinct purchase DAYS, because
--    ~29% of multi-order customers only placed several orders on one day
--    (split baskets), which is not a repeat purchase.
-- ---------------------------------------------------------------------
CREATE TABLE analytics.dim_customers AS
WITH v AS (
    SELECT f.* FROM analytics.fct_orders f, analytics.params pr
    WHERE f.is_valid AND f.purchase_ts < pr.window_end
), agg AS (
    SELECT customer_unique_id,
           MIN(purchase_ts)                                  AS first_purchase_ts,
           MAX(purchase_ts)                                  AS last_purchase_ts,
           DATE_TRUNC('month', MIN(purchase_ts))::date       AS cohort_month,
           COUNT(*)                                          AS n_orders,
           COUNT(DISTINCT purchase_ts::date)                 AS n_purchase_days,
           SUM(gmv)                                          AS total_gmv,
           SUM(order_value)                                  AS total_order_value,
           AVG(gmv)                                          AS avg_order_gmv,
           (ARRAY_AGG(customer_state ORDER BY purchase_ts DESC, order_id))[1] AS customer_state
    FROM v GROUP BY customer_unique_id
), first_order AS (
    SELECT customer_unique_id, review_score AS first_review_score,
           is_on_time AS first_on_time, days_vs_estimate AS first_days_vs_estimate,
           gmv AS first_order_gmv, used_voucher AS first_used_voucher
    FROM v WHERE valid_order_seq = 1
), thresholds AS (
    SELECT PERCENTILE_CONT((SELECT high_value_pctl FROM analytics.params))
           WITHIN GROUP (ORDER BY total_gmv) AS high_value_gmv
    FROM agg
)
SELECT a.*,
       f.first_review_score, f.first_on_time, f.first_days_vs_estimate, f.first_order_gmv,
       f.first_used_voucher,
       (pr.snapshot_date - a.last_purchase_ts::date)          AS recency_days,
       a.n_purchase_days >= 2                                 AS is_repeat,
       a.total_gmv >= t.high_value_gmv                        AS is_high_value,
       (pr.snapshot_date - a.last_purchase_ts::date) > pr.inactive_days AS is_potentially_inactive,
       -- RFM scores (5 = best). F is capped because 97% of customers have F=1.
       6 - NTILE(5) OVER (ORDER BY (pr.snapshot_date - a.last_purchase_ts::date), a.customer_unique_id) AS r_score,
       LEAST(a.n_purchase_days, 3)                            AS f_score,
       NTILE(5) OVER (ORDER BY a.total_gmv, a.customer_unique_id) AS m_score,
       CASE WHEN a.n_purchase_days >= 3 THEN '1. Frequent (3+ purchase days)'
            WHEN a.n_purchase_days = 2  THEN '2. Repeat (2 purchase days)'
            WHEN a.total_gmv >= t.high_value_gmv THEN '3. High-value one-time'
            WHEN (pr.snapshot_date - a.last_purchase_ts::date) <= 90  THEN '4. New one-time (<=90d)'
            WHEN (pr.snapshot_date - a.last_purchase_ts::date) <= pr.inactive_days THEN '5. One-time cooling (91-180d)'
            ELSE '6. One-time potentially inactive (>180d)' END  AS segment
FROM agg a
JOIN first_order f USING (customer_unique_id)
CROSS JOIN thresholds t
CROSS JOIN analytics.params pr;

ALTER TABLE analytics.dim_customers ADD PRIMARY KEY (customer_unique_id);
CREATE INDEX ON analytics.dim_customers (cohort_month);

-- ---------------------------------------------------------------------
-- 4. Purchase gaps: days between consecutive distinct purchase days
-- ---------------------------------------------------------------------
CREATE VIEW analytics.v_purchase_gaps AS
WITH days AS (
    SELECT DISTINCT f.customer_unique_id, f.purchase_ts::date AS d
    FROM analytics.fct_orders f, analytics.params pr
    WHERE f.is_valid AND f.purchase_ts < pr.window_end
), g AS (
    SELECT customer_unique_id, d,
           d - LAG(d) OVER (PARTITION BY customer_unique_id ORDER BY d) AS gap_days,
           ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY d) AS purchase_n
    FROM days
)
SELECT * FROM g WHERE gap_days IS NOT NULL;

-- Segment thresholds (documented, data-driven)
CREATE VIEW analytics.v_segment_thresholds AS
SELECT (SELECT PERCENTILE_CONT(pr.high_value_pctl) WITHIN GROUP (ORDER BY total_gmv)
          FROM analytics.dim_customers)                                         AS high_value_gmv_threshold,
       pr.inactive_days,
       (SELECT PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY gap_days) FROM analytics.v_purchase_gaps) AS median_gap_days,
       (SELECT PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY gap_days) FROM analytics.v_purchase_gaps) AS p75_gap_days,
       (SELECT PERCENTILE_CONT(0.9)  WITHIN GROUP (ORDER BY gap_days) FROM analytics.v_purchase_gaps) AS p90_gap_days
FROM analytics.params pr;

-- At-risk valuable customers: repeat or high-value, silent longer than the
-- 75th percentile of observed repeat gaps (75% of repeats happen sooner).
CREATE VIEW analytics.v_at_risk_customers AS
SELECT c.*
FROM analytics.dim_customers c, analytics.v_segment_thresholds t
WHERE (c.is_repeat OR c.is_high_value)
  AND c.recency_days > t.p75_gap_days
  AND c.recency_days <= 365;

-- ---------------------------------------------------------------------
-- 5. Module A - KPI views (all restricted to the analysis window)
-- ---------------------------------------------------------------------
CREATE VIEW analytics.v_kpi_summary AS
SELECT COUNT(*)                                                     AS total_orders,
       COUNT(*) FILTER (WHERE is_valid)                             AS valid_orders,
       COUNT(*) FILTER (WHERE is_delivered)                         AS delivered_orders,
       COUNT(*) FILTER (WHERE is_canceled)                          AS canceled_orders,
       COUNT(*) FILTER (WHERE is_unavailable)                       AS unavailable_orders,
       ROUND(SUM(gmv) FILTER (WHERE is_valid), 2)                   AS gmv,
       ROUND(SUM(gmv) FILTER (WHERE is_delivered), 2)               AS delivered_gmv,
       ROUND(SUM(freight) FILTER (WHERE is_valid), 2)               AS freight,
       ROUND(SUM(payment_value) FILTER (WHERE is_valid), 2)         AS payment_value_valid,
       ROUND(SUM(payment_value), 2)                                 AS payment_value_all,
       ROUND(AVG(gmv) FILTER (WHERE is_valid), 2)                   AS aov_gmv,
       ROUND(AVG(order_value) FILTER (WHERE is_valid), 2)           AS aov_incl_freight,
       ROUND(AVG(n_items) FILTER (WHERE is_valid), 3)               AS items_per_order,
       ROUND(AVG(is_canceled::int), 5)                              AS cancellation_rate,
       ROUND(AVG((is_canceled OR is_unavailable)::int), 5)          AS failed_order_rate,
       ROUND(AVG(approval_hours), 2)                                AS avg_approval_hours,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delivery_days)::numeric, 2) AS median_delivery_days,
       ROUND(AVG(delivery_days), 2)                                 AS avg_delivery_days,
       ROUND(AVG(handover_days), 2)                                 AS avg_handover_days,
       ROUND(AVG(is_on_time::int), 4)                               AS on_time_rate,
       ROUND(AVG(review_score), 3)                                  AS avg_review_score,
       COUNT(DISTINCT customer_unique_id) FILTER (WHERE is_valid)   AS active_customers,
       MIN(purchase_ts)::date AS first_day, MAX(purchase_ts)::date AS last_day
FROM analytics.fct_orders WHERE in_window;

CREATE VIEW analytics.v_kpi_monthly AS
WITH m AS (
    SELECT f.purchase_month AS month,
           COUNT(*)                                                 AS total_orders,
           COUNT(*) FILTER (WHERE is_valid)                         AS valid_orders,
           COUNT(*) FILTER (WHERE is_canceled)                      AS canceled_orders,
           COUNT(*) FILTER (WHERE is_unavailable)                   AS unavailable_orders,
           SUM(gmv) FILTER (WHERE is_valid)                         AS gmv,
           SUM(freight) FILTER (WHERE is_valid)                     AS freight,
           SUM(payment_value) FILTER (WHERE is_valid)               AS payment_value,
           AVG(gmv) FILTER (WHERE is_valid)                         AS aov,
           AVG(n_items) FILTER (WHERE is_valid)                     AS items_per_order,
           AVG(is_canceled::int)                                    AS cancellation_rate,
           AVG((is_canceled OR is_unavailable)::int)                AS failed_order_rate,
           AVG(delivery_days)                                       AS avg_delivery_days,
           AVG(is_on_time::int)                                     AS on_time_rate,
           AVG(review_score)                                        AS avg_review_score,
           COUNT(DISTINCT customer_unique_id) FILTER (WHERE is_valid) AS active_customers,
           COUNT(DISTINCT customer_unique_id) FILTER (WHERE valid_order_seq = 1) AS new_customers
    FROM analytics.fct_orders f WHERE in_window
    GROUP BY 1
)
SELECT m.*,
       active_customers - new_customers                                         AS returning_customers,
       gmv / NULLIF(LAG(gmv) OVER w, 0) - 1                                     AS gmv_mom_growth,
       valid_orders::numeric / NULLIF(LAG(valid_orders) OVER w, 0) - 1          AS orders_mom_growth,
       aov / NULLIF(LAG(aov) OVER w, 0) - 1                                     AS aov_mom_growth,
       RANK() OVER (ORDER BY valid_orders DESC)                                 AS order_volume_rank,
       SUM(gmv) OVER (ORDER BY month)                                           AS cumulative_gmv
FROM m WINDOW w AS (ORDER BY month)
ORDER BY month;

-- Is GMV change driven by volume or by order value?
-- dGMV = dN*AOV_prev (volume) + dAOV*N_prev (value) + dN*dAOV (interaction)
CREATE VIEW analytics.v_gmv_decomposition AS
WITH k AS (
    SELECT month, valid_orders AS n, aov, gmv,
           LAG(valid_orders) OVER (ORDER BY month) AS n_prev,
           LAG(aov)          OVER (ORDER BY month) AS aov_prev,
           LAG(gmv)          OVER (ORDER BY month) AS gmv_prev
    FROM analytics.v_kpi_monthly
)
SELECT month, gmv, gmv - gmv_prev                AS gmv_change,
       (n - n_prev) * aov_prev                   AS volume_effect,
       (aov - aov_prev) * n_prev                 AS value_effect,
       (n - n_prev) * (aov - aov_prev)           AS interaction_effect
FROM k WHERE n_prev IS NOT NULL ORDER BY month;

-- Year-over-year on comparable months (Jan-Aug 2018 vs Jan-Aug 2017)
CREATE VIEW analytics.v_yoy_growth AS
WITH y AS (
    SELECT EXTRACT(YEAR FROM purchase_month)::int AS yr,
           COUNT(*) FILTER (WHERE is_valid)      AS valid_orders,
           SUM(gmv) FILTER (WHERE is_valid)      AS gmv,
           AVG(gmv) FILTER (WHERE is_valid)      AS aov,
           COUNT(DISTINCT customer_unique_id) FILTER (WHERE is_valid) AS customers
    FROM analytics.fct_orders
    WHERE in_window AND EXTRACT(MONTH FROM purchase_month) BETWEEN 1 AND 8
    GROUP BY 1
)
SELECT a.valid_orders AS orders_2017, b.valid_orders AS orders_2018,
       b.valid_orders::numeric / a.valid_orders - 1 AS orders_yoy,
       a.gmv AS gmv_2017, b.gmv AS gmv_2018, b.gmv / a.gmv - 1 AS gmv_yoy,
       a.aov AS aov_2017, b.aov AS aov_2018, b.aov / a.aov - 1 AS aov_yoy,
       a.customers AS customers_2017, b.customers AS customers_2018
FROM y a JOIN y b ON a.yr = 2017 AND b.yr = 2018;

-- Where are cancellations concentrated?
CREATE VIEW analytics.v_cancellations_by_state AS
SELECT customer_state, COUNT(*) AS orders,
       COUNT(*) FILTER (WHERE is_canceled)    AS canceled,
       COUNT(*) FILTER (WHERE is_unavailable) AS unavailable,
       AVG(is_canceled::int)                  AS cancellation_rate,
       AVG((is_canceled OR is_unavailable)::int) AS failed_order_rate
FROM analytics.fct_orders WHERE in_window
GROUP BY 1 ORDER BY orders DESC;

CREATE VIEW analytics.v_cancellations_by_category AS
-- order-category grain so a multi-item order is counted once per category
WITH oc AS (
    SELECT DISTINCT order_id, category, is_canceled, order_status
    FROM analytics.fct_order_items WHERE in_window
)
SELECT category, COUNT(*) AS orders_with_category,
       COUNT(*) FILTER (WHERE is_canceled) AS canceled,
       AVG(is_canceled::int) AS cancellation_rate
FROM oc GROUP BY 1 HAVING COUNT(*) >= 500 ORDER BY cancellation_rate DESC;

CREATE VIEW analytics.v_cancellations_by_status_stage AS
SELECT CASE WHEN o.order_approved_at IS NULL THEN 'before approval'
            WHEN o.order_delivered_carrier_date IS NULL THEN 'approved, before carrier handover'
            ELSE 'after carrier handover' END AS stage,
       COUNT(*) AS canceled_orders,
       SUM(f.gmv) AS gmv_of_canceled_with_items,
       COUNT(*) FILTER (WHERE f.has_items) AS canceled_with_items
FROM analytics.fct_orders f JOIN clean.orders o USING (order_id)
WHERE f.in_window AND f.is_canceled
GROUP BY 1 ORDER BY 2 DESC;

-- Delivery delay vs review score (association only)
CREATE VIEW analytics.v_delivery_vs_review AS
SELECT CASE WHEN days_vs_estimate <= -10 THEN '1. 10+ days early'
            WHEN days_vs_estimate <= -1  THEN '2. 1-9 days early'
            WHEN days_vs_estimate = 0    THEN '3. on estimate day'
            WHEN days_vs_estimate <= 3   THEN '4. 1-3 days late'
            WHEN days_vs_estimate <= 7   THEN '5. 4-7 days late'
            ELSE '6. 8+ days late' END    AS delivery_bucket,
       COUNT(*)                                  AS orders,
       AVG(review_score)                         AS avg_review_score,
       AVG((review_score <= 2)::int)             AS share_1_2_star,
       AVG((review_score = 5)::int)              AS share_5_star
FROM analytics.fct_orders
WHERE in_window AND is_delivered AND days_vs_estimate IS NOT NULL AND review_score IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- ---------------------------------------------------------------------
-- 6. Module B - Customer retention
-- ---------------------------------------------------------------------
CREATE VIEW analytics.v_customer_overview AS
SELECT COUNT(*)                                              AS customers,
       COUNT(*) FILTER (WHERE is_repeat)                     AS repeat_customers,
       AVG(is_repeat::int)                                   AS repeat_rate,
       AVG((n_orders >= 2)::int)                             AS repeat_rate_order_based,
       AVG(n_purchase_days)                                  AS avg_purchase_days,
       SUM(total_gmv) FILTER (WHERE is_repeat) / SUM(total_gmv) AS repeat_customer_gmv_share,
       AVG(total_gmv)                                        AS avg_customer_gmv,
       AVG(total_gmv) FILTER (WHERE is_repeat)               AS avg_repeat_customer_gmv,
       AVG(total_gmv) FILTER (WHERE NOT is_repeat)           AS avg_one_time_customer_gmv
FROM analytics.dim_customers;

CREATE VIEW analytics.v_order_frequency AS
SELECT LEAST(n_purchase_days, 5) AS purchase_days_capped, COUNT(*) AS customers,
       COUNT(*)::numeric / SUM(COUNT(*)) OVER () AS share,
       SUM(total_gmv) AS gmv
FROM analytics.dim_customers GROUP BY 1 ORDER BY 1;

-- Monthly cohort retention. Cohort = month of first valid purchase.
-- Cell (cohort, k) = share of cohort with >=1 valid order in month cohort+k.
-- Cells whose calendar month is after the last complete month are NULL
-- (unobservable), not zero.
CREATE VIEW analytics.v_cohort_retention AS
WITH act AS (
    SELECT DISTINCT f.customer_unique_id, f.purchase_month
    FROM analytics.fct_orders f, analytics.params pr
    WHERE f.is_valid AND f.purchase_ts < pr.window_end
), sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size
    FROM analytics.dim_customers c, analytics.params pr
    WHERE cohort_month >= pr.window_start GROUP BY 1
), grid AS (
    SELECT s.cohort_month, s.cohort_size, k
    FROM sizes s CROSS JOIN GENERATE_SERIES(0, 19) AS k
), cnt AS (
    SELECT c.cohort_month,
           ((EXTRACT(YEAR FROM a.purchase_month) - EXTRACT(YEAR FROM c.cohort_month)) * 12
            + EXTRACT(MONTH FROM a.purchase_month) - EXTRACT(MONTH FROM c.cohort_month))::int AS k,
           COUNT(DISTINCT a.customer_unique_id) AS active
    FROM analytics.dim_customers c JOIN act a USING (customer_unique_id)
    GROUP BY 1, 2
)
SELECT g.cohort_month, g.cohort_size, g.k AS months_since_first,
       (g.cohort_month + MAKE_INTERVAL(months => g.k))::date < pr.window_end AS is_observable,
       CASE WHEN (g.cohort_month + MAKE_INTERVAL(months => g.k))::date < pr.window_end
            THEN COALESCE(cnt.active, 0) END AS active_customers,
       CASE WHEN (g.cohort_month + MAKE_INTERVAL(months => g.k))::date < pr.window_end
            THEN COALESCE(cnt.active, 0)::numeric / g.cohort_size END AS retention_rate
FROM grid g
LEFT JOIN cnt USING (cohort_month, k)
CROSS JOIN analytics.params pr
ORDER BY 1, 3;

-- Cumulative repeat within N days of first purchase, only for cohorts with
-- a full N-day observation window (right-censoring handled explicitly).
CREATE VIEW analytics.v_repeat_within_days AS
WITH second AS (
    SELECT customer_unique_id, MIN(d) AS second_day
    FROM (SELECT customer_unique_id, d, ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY d) rn
          FROM (SELECT DISTINCT customer_unique_id, purchase_ts::date d
                FROM analytics.fct_orders f, analytics.params pr
                WHERE f.is_valid AND f.purchase_ts < pr.window_end) x) y
    WHERE rn = 2 GROUP BY 1
)
SELECT n AS horizon_days,
       COUNT(*) AS eligible_customers,
       AVG(COALESCE(s.second_day - c.first_purchase_ts::date <= n, FALSE)::int) AS repeat_rate  -- no 2nd purchase = not repeated
FROM analytics.dim_customers c
LEFT JOIN second s USING (customer_unique_id)
CROSS JOIN (VALUES (30), (60), (90), (180), (365)) h(n)
CROSS JOIN analytics.params pr
WHERE c.first_purchase_ts::date + n < pr.window_end AND c.cohort_month >= pr.window_start
GROUP BY n ORDER BY n;

CREATE VIEW analytics.v_customer_segments AS
SELECT segment,
       COUNT(*)                                   AS customers,
       COUNT(*)::numeric / SUM(COUNT(*)) OVER ()  AS share_customers,
       SUM(total_gmv)                             AS gmv,
       SUM(total_gmv) / SUM(SUM(total_gmv)) OVER () AS share_gmv,
       AVG(total_gmv)                             AS avg_gmv,
       AVG(n_purchase_days)                       AS avg_purchase_days,
       AVG(recency_days)                          AS avg_recency_days,
       AVG(first_review_score)                    AS avg_first_review
FROM analytics.dim_customers GROUP BY 1 ORDER BY 1;

-- First-experience vs repeat (association only)
CREATE VIEW analytics.v_first_experience_vs_repeat AS
SELECT CASE WHEN first_review_score IS NULL THEN 'no review'
            WHEN first_review_score <= 2 THEN '1-2 stars'
            WHEN first_review_score = 3 THEN '3 stars'
            ELSE '4-5 stars' END AS first_review,
       CASE WHEN first_on_time IS NULL THEN 'not delivered/unknown'
            WHEN first_on_time THEN 'on time' ELSE 'late' END AS first_delivery,
       COUNT(*) AS customers, AVG(is_repeat::int) AS repeat_rate
FROM analytics.dim_customers c, analytics.params pr
WHERE c.first_purchase_ts < pr.window_end - 180   -- >=180 days to observe a repeat
GROUP BY 1, 2 ORDER BY 1, 2;

-- ---------------------------------------------------------------------
-- 7. Module C - Category & seller performance (valid orders, in window)
-- ---------------------------------------------------------------------
CREATE VIEW analytics.v_category_performance AS
WITH it AS (
    SELECT * FROM analytics.fct_order_items WHERE in_window AND is_valid
), oc AS (   -- order x category grain for order-level attributes (review, delivery)
    SELECT DISTINCT order_id, category, review_score, is_on_time, delivery_days
    FROM it
), base AS (
    SELECT category,
           SUM(price)                    AS gmv,
           COUNT(*)                      AS items,
           COUNT(DISTINCT order_id)      AS orders,
           AVG(price)                    AS avg_item_price,
           AVG(freight_value / price)    AS avg_freight_to_price,
           COUNT(DISTINCT seller_id)     AS sellers,
           COUNT(DISTINCT product_id)    AS products,
           SUM(price) FILTER (WHERE purchase_month BETWEEN '2017-01-01' AND '2017-08-01') AS gmv_jan_aug_2017,
           SUM(price) FILTER (WHERE purchase_month BETWEEN '2018-01-01' AND '2018-08-01') AS gmv_jan_aug_2018
    FROM it GROUP BY 1
), qual AS (
    SELECT category, AVG(review_score) AS avg_review, AVG((review_score <= 2)::int) AS share_1_2_star,
           AVG(is_on_time::int) AS on_time_rate, AVG(delivery_days) AS avg_delivery_days
    FROM oc GROUP BY 1
)
SELECT b.*, q.avg_review, q.share_1_2_star, q.on_time_rate, q.avg_delivery_days,
       b.gmv / SUM(b.gmv) OVER ()                                  AS gmv_share,
       SUM(b.gmv) OVER (ORDER BY b.gmv DESC) / SUM(b.gmv) OVER ()  AS cumulative_gmv_share,
       b.gmv_jan_aug_2018 / NULLIF(b.gmv_jan_aug_2017, 0) - 1      AS gmv_yoy_growth,
       RANK() OVER (ORDER BY b.gmv DESC)                           AS gmv_rank,
       RANK() OVER (ORDER BY q.avg_review DESC)                    AS review_rank
FROM base b JOIN qual q USING (category)
ORDER BY gmv DESC;

CREATE VIEW analytics.v_category_monthly AS
SELECT purchase_month AS month, category, SUM(price) AS gmv, COUNT(*) AS items,
       COUNT(DISTINCT order_id) AS orders
FROM analytics.fct_order_items WHERE in_window AND is_valid
GROUP BY 1, 2;

CREATE VIEW analytics.v_seller_concentration AS
WITH s AS (
    SELECT seller_id, SUM(price) AS gmv, COUNT(DISTINCT order_id) AS orders
    FROM analytics.fct_order_items WHERE in_window AND is_valid GROUP BY 1
), r AS (
    SELECT s.*, ROW_NUMBER() OVER (ORDER BY gmv DESC) AS rnk, COUNT(*) OVER () AS n,
           gmv / SUM(gmv) OVER () AS share
    FROM s
)
SELECT MAX(n)                                              AS sellers,
       SUM(share) FILTER (WHERE rnk <= CEIL(n * 0.01))     AS top1pct_share,
       SUM(share) FILTER (WHERE rnk <= CEIL(n * 0.10))     AS top10pct_share,
       SUM(share) FILTER (WHERE rnk <= CEIL(n * 0.20))     AS top20pct_share,
       SUM(share * share) * 10000                          AS hhi,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY orders) AS median_orders_per_seller
FROM r;

CREATE VIEW analytics.v_review_distribution AS
SELECT review_score, COUNT(*) AS orders, COUNT(*)::numeric / SUM(COUNT(*)) OVER () AS share
FROM analytics.fct_orders WHERE in_window AND is_valid AND review_score IS NOT NULL
GROUP BY 1 ORDER BY 1;
