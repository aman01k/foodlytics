-- Module C: Product category & seller performance (proxy for restaurant/cuisine analytics).

-- name: c01_category_ranking
SELECT gmv_rank, category, ROUND(gmv, 0) AS gmv, ROUND(100 * gmv_share, 2) AS gmv_share_pct,
       ROUND(100 * cumulative_gmv_share, 1) AS cum_share_pct, items, orders,
       ROUND(avg_item_price, 2) AS avg_item_price, sellers,
       ROUND(100 * gmv_yoy_growth, 1) AS gmv_yoy_pct,
       ROUND(avg_review, 2) AS avg_review, ROUND(100 * share_1_2_star, 1) AS pct_1_2_star,
       ROUND(100 * on_time_rate, 1) AS on_time_pct, ROUND(avg_delivery_days, 1) AS avg_delivery_days
FROM analytics.v_category_performance ORDER BY gmv_rank;

-- name: c02_pareto
-- How many categories make up 80% of GMV?
SELECT COUNT(*) FILTER (WHERE cumulative_gmv_share <= 0.80) + 1 AS categories_for_80pct_gmv,
       COUNT(*) AS total_categories
FROM analytics.v_category_performance;

-- name: c03_growth_leaders_laggards
-- Among material categories (>=1% GMV share), fastest/slowest YoY growth (Jan-Aug).
(SELECT 'fastest' AS grp, category, ROUND(100 * gmv_share, 2) AS gmv_share_pct, ROUND(100 * gmv_yoy_growth, 1) AS yoy_pct
 FROM analytics.v_category_performance WHERE gmv_share >= 0.01 ORDER BY gmv_yoy_growth DESC LIMIT 5)
UNION ALL
(SELECT 'slowest', category, ROUND(100 * gmv_share, 2), ROUND(100 * gmv_yoy_growth, 1)
 FROM analytics.v_category_performance WHERE gmv_share >= 0.01 ORDER BY gmv_yoy_growth ASC LIMIT 5);

-- name: c04_quality_risk_categories
-- Material categories with the worst review profile, with delivery indicators.
SELECT category, ROUND(100 * gmv_share, 2) AS gmv_share_pct, ROUND(avg_review, 2) AS avg_review,
       ROUND(100 * share_1_2_star, 1) AS pct_1_2_star, ROUND(100 * on_time_rate, 1) AS on_time_pct,
       ROUND(avg_delivery_days, 1) AS avg_delivery_days
FROM analytics.v_category_performance WHERE gmv_share >= 0.01 ORDER BY avg_review ASC LIMIT 8;

-- name: c05_seller_concentration
SELECT sellers, ROUND(100 * top1pct_share, 1) AS top1pct_gmv_share, ROUND(100 * top10pct_share, 1) AS top10pct_gmv_share,
       ROUND(100 * top20pct_share, 1) AS top20pct_gmv_share, ROUND(hhi, 1) AS hhi, median_orders_per_seller
FROM analytics.v_seller_concentration;

-- name: c06_category_seller_concentration
-- Dependence of each top-15 category on its single largest seller.
WITH s AS (
    SELECT category, seller_id, SUM(price) AS gmv
    FROM analytics.fct_order_items WHERE in_window AND is_valid GROUP BY 1, 2
), r AS (
    SELECT s.*, gmv / SUM(gmv) OVER (PARTITION BY category) AS share,
           ROW_NUMBER() OVER (PARTITION BY category ORDER BY gmv DESC) AS rn
    FROM s
)
SELECT p.gmv_rank, r.category, ROUND(100 * MAX(share) FILTER (WHERE rn = 1), 1) AS top_seller_share_pct,
       ROUND(100 * SUM(share) FILTER (WHERE rn <= 3), 1) AS top3_sellers_share_pct
FROM r JOIN analytics.v_category_performance p USING (category)
WHERE p.gmv_rank <= 15 GROUP BY 1, 2 ORDER BY 1;

-- name: c07_review_distribution
SELECT review_score, orders, ROUND(100 * share, 1) AS share_pct FROM analytics.v_review_distribution;

-- name: c08_price_band_mix
SELECT CASE WHEN price < 50 THEN '1. <R$50' WHEN price < 100 THEN '2. R$50-99'
            WHEN price < 200 THEN '3. R$100-199' WHEN price < 500 THEN '4. R$200-499' ELSE '5. R$500+' END AS price_band,
       COUNT(*) AS items, ROUND(SUM(price), 0) AS gmv,
       ROUND(100.0 * SUM(price) / SUM(SUM(price)) OVER (), 1) AS gmv_share_pct,
       ROUND(AVG(review_score), 2) AS avg_review
FROM analytics.fct_order_items WHERE in_window AND is_valid GROUP BY 1 ORDER BY 1;
