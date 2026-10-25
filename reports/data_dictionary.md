# Data dictionary

**Source:** [Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). It holds about 100k marketplace orders placed between Sep 2016 and Oct 2018.

**This is an e-commerce proxy, not food-delivery data.** The table below maps each Olist concept to its nearest food-delivery equivalent, along with what does not transfer.

| Olist concept | Food-delivery analogue | Key difference |
|---|---|---|
| Order | Order | Olist delivery takes about 10 days; food delivery takes about 30 minutes. |
| Seller | Restaurant | Olist sellers ship nationally. |
| Product category | Cuisine / restaurant type | **Not equivalent.** Categories describe products, not cuisines. |
| Estimated delivery date | Promised ETA | Different scale and mechanism. |
| Purchase frequency | Ordering frequency | Food is weekly; Olist is mostly one-off (97.8% of customers buy once). |

## Layers (PostgreSQL database `foodlytics`)

| Schema | Contents | Built by |
|---|---|---|
| `raw` | The 9 CSVs loaded verbatim, all columns `TEXT` | `src/load_postgres.py` |
| `clean` | Typed tables with PK/FK/CHECK constraints and indexes | `src/clean_data.py` → `sql/schema.sql` |
| `analytics` | Fact/dimension tables, KPI views, experiment and sizing outputs | `sql/analytical_views.sql`, `src/experiment_analysis.py`, `src/opportunity_sizing.py` |

## `clean` schema

| Table | Grain / PK | Rows | Notes |
|---|---|---|---|
| `orders` | `order_id` | 99,441 | FK → customers. Six `flag_*` timestamp-anomaly columns plus `has_timestamp_anomaly` (1,396 rows flagged; none dropped). |
| `order_items` | (`order_id`, `order_item_id`) | 112,650 | FK → orders, products, sellers. `price > 0`, `freight ≥ 0`. |
| `order_payments` | (`order_id`, `payment_sequential`) | 103,886 | 9 zero-value rows (`flag_zero_value`) and 2 with zero installments (`flag_invalid_installments`) are kept. |
| `order_reviews` | `order_id` | 98,673 | One review per order: the latest answered. 551 superseded reviews were removed. `review_id` is **not** unique in the source (814 ids are reused across orders). |
| `customers` | `customer_id` | 99,441 | `customer_id` is per order; `customer_unique_id` (96,096 distinct) identifies the account. |
| `products` | `product_id` | 32,951 | `*_lenght` typos renamed to `*_length`. 610 missing categories set to `unknown`. 4 zero-gram weights set to NULL. |
| `product_categories` | `product_category_name` | 74 | The 71 official translations plus 3 added: `pc_gamer`, `portateis_cozinha_e_preparadores_de_alimentos` (missing from the official file), and `unknown`. |
| `sellers` | `seller_id` | 3,095 | |
| `geolocation` | `zip_code_prefix` | 19,010 | 1,000,163 raw rows → 261,831 exact duplicates removed and 33 points outside Brazil dropped. Aggregated to one row per prefix (median lat/lng, modal city/state). |

Customer and seller zip prefixes are kept as zero-padded `CHAR(5)`. Some prefixes have no geolocation row, so that foreign key is deliberately not enforced.

## `analytics` schema (main objects)

| Object | Type | Grain | Purpose |
|---|---|---|---|
| `params` | table | 1 row | Window, snapshot and segment thresholds. |
| `fct_orders` | table | order | Order-level fact: status flags, GMV, freight, payments, delivery metrics, review, `in_window`, `valid_order_seq`. |
| `fct_order_items` | view | item | Items with category and order context. |
| `dim_customers` | table | customer_unique_id | First/last purchase, cohort, frequency (distinct days), monetary, recency, RFM scores, segment. |
| `v_kpi_summary`, `v_kpi_monthly`, `v_yoy_growth`, `v_gmv_decomposition` | views | — | Module A KPIs. |
| `v_cancellations_by_*`, `v_delivery_vs_review` | views | — | Module A diagnostics. |
| `v_customer_overview`, `v_order_frequency`, `v_cohort_retention`, `v_repeat_within_days`, `v_purchase_gaps`, `v_segment_thresholds`, `v_customer_segments`, `v_at_risk_customers`, `v_first_experience_vs_repeat` | views | — | Module B. |
| `v_category_performance`, `v_category_monthly`, `v_seller_concentration`, `v_review_distribution` | views | — | Module C. |
| `exp_customers`, `exp_group_summary`, `exp_sens_*`, `exp_monte_carlo` | tables | — | **SYNTHETIC** experiment outputs (`is_synthetic = true`). |
| `opportunity_sizing` | table | opportunity × scenario | Module E scenarios. |

### Key `fct_orders` columns

| Column | Meaning |
|---|---|
| `is_valid` | Not canceled/unavailable and has items. |
| `gmv`, `freight`, `order_value`, `payment_value` | See `metric_definitions.md`. |
| `approval_hours`, `handover_days`, `delivery_days` | NULL when the timestamps are missing or invalid. |
| `is_on_time`, `days_vs_estimate` | Delivered orders only. |
| `valid_order_seq` | 1 = the customer's first valid order (ties broken by `order_id`). |
| `in_window` | Purchase date between 2017-01-01 and 2018-08-31. |

## Data-quality findings (from `src/clean_data.py` / `cleaning_report.json`)

* No duplicate primary keys in any source table. No orphan foreign keys.
* 775 orders have no items: 603 `unavailable`, 164 `canceled`, 5 `created`, 2 `invoiced`, 1 `shipped`.
* 1 order has no payment record.
* Timestamp anomalies are flagged, not dropped:
  * carrier handover before approval: 1,359
  * carrier handover before purchase: 166
  * customer delivery before carrier handover: 23
  * `delivered` status with no delivery date: 8
  * delivery date on a non-delivered (canceled) order: 6
* Payments differ from items + freight by more than R$1 on 0.25% of orders. The causes are installment interest and vouchers.
