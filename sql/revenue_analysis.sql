-- Module A: Revenue & business performance. Each `-- name:` block is executed by
-- src/metrics.py and its output saved to reports/results/<name>.csv.

-- name: a01_kpi_summary
-- Headline KPIs for the analysis window (Jan 2017 - Aug 2018).
SELECT * FROM analytics.v_kpi_summary;

-- name: a02_monthly_kpis
-- Q: Is the business growing? Which months have the highest volume?
SELECT month, valid_orders, ROUND(gmv, 0) AS gmv, ROUND(aov, 2) AS aov,
       ROUND(100 * gmv_mom_growth, 1) AS gmv_mom_pct, ROUND(100 * orders_mom_growth, 1) AS orders_mom_pct,
       ROUND(100 * cancellation_rate, 2) AS cancel_pct, ROUND(100 * on_time_rate, 1) AS on_time_pct,
       ROUND(avg_delivery_days, 1) AS avg_delivery_days, ROUND(avg_review_score, 2) AS avg_review,
       new_customers, returning_customers, order_volume_rank
FROM analytics.v_kpi_monthly;

-- name: a03_yoy_growth
-- Comparable-period growth (Jan-Aug 2018 vs Jan-Aug 2017) avoids seasonality bias.
SELECT * FROM analytics.v_yoy_growth;

-- name: a04_gmv_drivers
-- Q: Are revenue changes driven by order volume or order value?
-- Sum of absolute monthly effects shows which lever moved GMV more.
SELECT ROUND(SUM(ABS(volume_effect)), 0)                    AS abs_volume_effect,
       ROUND(SUM(ABS(value_effect)), 0)                     AS abs_value_effect,
       ROUND(SUM(ABS(interaction_effect)), 0)               AS abs_interaction_effect,
       ROUND(SUM(ABS(volume_effect)) / SUM(ABS(volume_effect) + ABS(value_effect) + ABS(interaction_effect)), 3) AS volume_share_of_movement,
       CORR(gmv_change, volume_effect)                      AS corr_gmv_change_volume,
       CORR(gmv_change, value_effect)                       AS corr_gmv_change_value
FROM analytics.v_gmv_decomposition;

-- name: a05_top_months
SELECT month, valid_orders, ROUND(gmv, 0) AS gmv, order_volume_rank
FROM analytics.v_kpi_monthly WHERE order_volume_rank <= 5 ORDER BY order_volume_rank;

-- name: a06_weekday_hour_profile
-- When do customers order? (useful for campaign timing)
SELECT EXTRACT(ISODOW FROM purchase_ts)::int AS iso_weekday,
       COUNT(*) FILTER (WHERE is_valid) AS valid_orders,
       ROUND(AVG(gmv) FILTER (WHERE is_valid), 2) AS aov
FROM analytics.fct_orders WHERE in_window GROUP BY 1 ORDER BY 1;

-- name: a07_cancellations_by_stage
-- Q: Where are cancellations concentrated (order lifecycle stage)?
SELECT * FROM analytics.v_cancellations_by_status_stage;

-- name: a08_cancellations_by_state
SELECT customer_state, orders, canceled, unavailable,
       ROUND(100 * cancellation_rate, 2) AS cancel_pct, ROUND(100 * failed_order_rate, 2) AS failed_pct
FROM analytics.v_cancellations_by_state WHERE orders >= 1000 ORDER BY failed_order_rate DESC;

-- name: a09_cancellations_by_month
SELECT month, total_orders, canceled_orders, unavailable_orders,
       ROUND(100 * cancellation_rate, 2) AS cancel_pct, ROUND(100 * failed_order_rate, 2) AS failed_pct
FROM analytics.v_kpi_monthly ORDER BY month;

-- name: a10_cancellations_by_category
SELECT category, orders_with_category, canceled, ROUND(100 * cancellation_rate, 2) AS cancel_pct
FROM analytics.v_cancellations_by_category LIMIT 15;

-- name: a11_delivery_vs_review
-- Q: Are delivery delays associated with lower review scores? (association, not causation)
SELECT delivery_bucket, orders, ROUND(avg_review_score, 2) AS avg_review,
       ROUND(100 * share_1_2_star, 1) AS pct_1_2_star, ROUND(100 * share_5_star, 1) AS pct_5_star
FROM analytics.v_delivery_vs_review;

-- name: a12_late_vs_ontime_review
-- Two-group summary used for a significance test in src/metrics.py
SELECT is_on_time, COUNT(*) AS orders, ROUND(AVG(review_score), 3) AS avg_review,
       ROUND(STDDEV(review_score), 3) AS sd_review
FROM analytics.fct_orders
WHERE in_window AND is_delivered AND is_on_time IS NOT NULL AND review_score IS NOT NULL
GROUP BY 1;

-- name: a13_payment_mix
SELECT primary_payment_type, COUNT(*) AS orders, ROUND(AVG(gmv), 2) AS aov,
       ROUND(AVG(max_installments), 2) AS avg_installments,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_pct
FROM analytics.fct_orders WHERE in_window AND is_valid GROUP BY 1 ORDER BY orders DESC;

-- name: a14_state_performance
-- Ranking states by GMV with delivery quality (window functions)
SELECT customer_state, COUNT(*) AS orders, ROUND(SUM(gmv), 0) AS gmv,
       ROUND(100 * SUM(gmv) / SUM(SUM(gmv)) OVER (), 2) AS gmv_share_pct,
       ROUND(AVG(delivery_days), 1) AS avg_delivery_days,
       ROUND(100 * AVG(is_on_time::int), 1) AS on_time_pct,
       ROUND(AVG(review_score), 2) AS avg_review,
       DENSE_RANK() OVER (ORDER BY SUM(gmv) DESC) AS gmv_rank
FROM analytics.fct_orders WHERE in_window AND is_valid
GROUP BY 1 ORDER BY gmv DESC;
