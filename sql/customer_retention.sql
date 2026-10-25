-- Module B: Customer retention & cohorts.

-- name: b01_customer_overview
SELECT * FROM analytics.v_customer_overview;

-- name: b02_order_frequency
SELECT purchase_days_capped, customers, ROUND(100 * share, 3) AS share_pct, ROUND(gmv, 0) AS gmv
FROM analytics.v_order_frequency;

-- name: b03_monthly_new_vs_returning
SELECT month, active_customers, new_customers, returning_customers,
       ROUND(100.0 * returning_customers / active_customers, 2) AS returning_pct
FROM analytics.v_kpi_monthly ORDER BY month;

-- name: b04_cohort_retention_matrix
-- Long format; pivoted in Python/dashboard. NULL = not yet observable.
SELECT cohort_month, cohort_size, months_since_first, active_customers, retention_rate
FROM analytics.v_cohort_retention ORDER BY cohort_month, months_since_first;

-- name: b05_cohort_retention_summary
-- Average retention at month k across cohorts that can be observed at k,
-- weighted by cohort size (avoids small cohorts dominating).
SELECT months_since_first,
       COUNT(*)                                               AS cohorts_observed,
       SUM(cohort_size)                                       AS customers_observed,
       ROUND(100 * SUM(active_customers)::numeric / SUM(cohort_size), 3) AS weighted_retention_pct
FROM analytics.v_cohort_retention
WHERE is_observable AND months_since_first BETWEEN 1 AND 12
GROUP BY 1 ORDER BY 1;

-- name: b06_cohort_m1_m3_ranking
-- Q: Which acquisition cohorts retain better? Cumulative 3-month repeat rate
-- (any repeat in months 1-3), only for cohorts with 3 observable months.
WITH rep AS (
    SELECT DISTINCT d.customer_unique_id
    FROM analytics.dim_customers d
    JOIN analytics.fct_orders f USING (customer_unique_id)
    WHERE f.is_valid
      AND f.purchase_month >  d.cohort_month
      AND f.purchase_month <= (d.cohort_month + INTERVAL '3 months')::date
), c AS (
    SELECT d.cohort_month, r.customer_unique_id IS NOT NULL AS repeat_m1_3
    FROM analytics.dim_customers d
    LEFT JOIN rep r USING (customer_unique_id)
    CROSS JOIN analytics.params p
    WHERE d.cohort_month >= p.window_start
      AND (d.cohort_month + INTERVAL '3 months')::date < p.window_end
)
SELECT cohort_month, COUNT(*) AS cohort_size,
       ROUND(100 * AVG(repeat_m1_3::int), 3) AS repeat_m1_3_pct,
       RANK() OVER (ORDER BY AVG(repeat_m1_3::int) DESC) AS rank
FROM c GROUP BY 1 ORDER BY 1;

-- name: b07_repeat_within_days
SELECT horizon_days, eligible_customers, ROUND(100 * repeat_rate, 3) AS repeat_pct
FROM analytics.v_repeat_within_days;

-- name: b08_purchase_gap_distribution
SELECT CASE WHEN gap_days <= 7 THEN '01. 1-7d' WHEN gap_days <= 30 THEN '02. 8-30d'
            WHEN gap_days <= 60 THEN '03. 31-60d' WHEN gap_days <= 90 THEN '04. 61-90d'
            WHEN gap_days <= 180 THEN '05. 91-180d' WHEN gap_days <= 365 THEN '06. 181-365d'
            ELSE '07. >365d' END AS gap_bucket,
       COUNT(*) AS repeat_purchases,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_pct,
       ROUND(100.0 * SUM(COUNT(*)) OVER (ORDER BY MIN(gap_days)) / SUM(COUNT(*)) OVER (), 1) AS cumulative_pct
FROM analytics.v_purchase_gaps GROUP BY 1 ORDER BY 1;

-- name: b09_segment_thresholds
SELECT * FROM analytics.v_segment_thresholds;

-- name: b10_segments
SELECT segment, customers, ROUND(100 * share_customers, 2) AS customers_pct,
       ROUND(gmv, 0) AS gmv, ROUND(100 * share_gmv, 2) AS gmv_pct,
       ROUND(avg_gmv, 2) AS avg_gmv, ROUND(avg_recency_days, 0) AS avg_recency_days,
       ROUND(avg_first_review, 2) AS avg_first_review
FROM analytics.v_customer_segments;

-- name: b11_rfm_grid
SELECT r_score, m_score, COUNT(*) AS customers, ROUND(AVG(total_gmv), 2) AS avg_gmv,
       ROUND(100 * AVG(is_repeat::int), 2) AS repeat_pct
FROM analytics.dim_customers GROUP BY 1, 2 ORDER BY 1 DESC, 2 DESC;

-- name: b12_at_risk_customers
SELECT COUNT(*) AS at_risk_customers, ROUND(SUM(total_gmv), 0) AS historical_gmv,
       ROUND(AVG(recency_days), 0) AS avg_recency, COUNT(*) FILTER (WHERE is_repeat) AS of_which_repeat
FROM analytics.v_at_risk_customers;

-- name: b13_first_experience_vs_repeat
-- Association between first-order experience and later repeat (>=180d observed).
SELECT * FROM analytics.v_first_experience_vs_repeat;

-- name: b14_repeat_by_state
SELECT customer_state, COUNT(*) AS customers, ROUND(100 * AVG(is_repeat::int), 2) AS repeat_pct
FROM analytics.dim_customers GROUP BY 1 HAVING COUNT(*) >= 1000 ORDER BY repeat_pct DESC;
