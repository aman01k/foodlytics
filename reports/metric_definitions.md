# Metric definitions

Every metric is defined once here and computed once in SQL (`sql/analytical_views.sql`). The dashboard, notebooks and reports all read those views, so a number means the same thing everywhere. The parameters live in one table, `analytics.params`.

## Global conventions

| Item | Definition | Why |
|---|---|---|
| Analysis window | Orders purchased **2017-01-01 to 2018-08-31** (`in_window`) | 2016 has only 329 orders with a two-month gap (platform ramp-up). Sep–Oct 2018 has 20 orders, so the data stops there. Both would distort monthly growth rates. |
| Snapshot date | 2018-09-01 | This is "today" when computing recency. |
| Last 12 months (LTM) | 2017-09-01 to 2018-08-31 | Used for annualised opportunity sizing. |
| Currency | BRL (R$), nominal | Olist values are not inflation-adjusted. |
| Order identity | `order_id` | Unique in the source. |
| Customer identity | `customer_unique_id` | Olist's `customer_id` is created **per order** (99,441 ids for 96,096 people/accounts). `customer_unique_id` is the closest thing to a person, but it is an account proxy, not a verified individual. |

## Order status groups

| Group | Statuses | Used for |
|---|---|---|
| **Valid order** | not `canceled`/`unavailable` **and** has ≥1 line item | All revenue, AOV and customer metrics. It includes in-flight orders (shipped, invoiced, processing, approved) because those are real purchases. |
| Delivered | `delivered` | Delivery-time and on-time metrics. |
| Canceled | `canceled` | Cancellation rate. |
| Failed | `canceled` + `unavailable` | Failed-order rate. `unavailable` orders almost never have line items (603 of 609), so their value cannot be observed. |

## Revenue metrics. These are not interchangeable.

| Metric | Formula | Notes |
|---|---|---|
| **GMV** | Σ `order_items.price` over valid orders | The primary "revenue proxy". Excludes freight. It is merchandise value, **not** Olist's revenue. |
| Freight | Σ `order_items.freight_value` over valid orders | Reported separately. |
| Order value | GMV + freight | What the customer was charged before payment effects. |
| Payment value | Σ `order_payments.payment_value` | Includes freight, installment interest and vouchers. It reconciles to order value within R$1 for 99.75% of orders. |
| Delivered GMV | GMV of `delivered` orders only | A conservative "realised" figure. |
| Seller revenue / platform revenue / profit | **Not observable** | Olist has no commission, cost or margin data. Any profit figure in this project is a scenario built on a stated assumption. |

**Double-counting guard:** items (item grain) and payments (payment grain) are each aggregated to order grain in separate CTEs before they are joined. Joining them first inflates GMV, which `tests/test_kpis.py::test_naive_join_would_double_count` demonstrates.

## Module A KPIs

| KPI | Definition |
|---|---|
| Total orders | All orders placed in the window, any status. |
| Valid orders | See above. |
| AOV | GMV / valid orders. |
| Items per order | Mean line items per valid order. |
| MoM growth | `value_t / value_{t-1} − 1` via `LAG()` over months. |
| YoY growth | Jan–Aug 2018 vs Jan–Aug 2017. These months are comparable, so seasonality cancels. |
| GMV decomposition | ΔGMV = ΔN·AOV₍t−1₎ (volume) + ΔAOV·N₍t−1₎ (value) + ΔN·ΔAOV (interaction). |
| Cancellation rate | canceled / total orders. |
| Failed-order rate | (canceled + unavailable) / total orders. |
| Approval time | `approved_at − purchase`, in hours. |
| Handover time | `carrier_date − purchase`, in days. NULL when the carrier date precedes the purchase, which happens in 166 flagged rows. |
| Delivery time | `delivered_customer_date − purchase`, in days. Delivered orders only. |
| **On-time delivery** | `delivered_date::date ≤ estimated_delivery_date::date`. The target is the delivery date Olist promised the customer at checkout. That makes it a defensible, customer-facing SLA rather than an arbitrary threshold. |
| Days vs estimate | `delivered_date − estimated_date`. A positive value means late. |

## Module B: customers

| Metric | Definition |
|---|---|
| Customer universe | `customer_unique_id`s with ≥1 valid order before 2018-09-01 (94,983). |
| Purchase frequency | Number of **distinct purchase days**. 29% of customers with 2+ orders placed them all on the same day (split baskets), and that is not a repeat purchase. The order-based rate is also reported. |
| Repeat customer | Purchases on ≥2 distinct days. |
| Repeat rate | Repeat customers / customers. |
| Repeat within N days | Share whose 2nd purchase day is ≤N days after the first. Only customers with a full N-day observation window are included, which handles right-censoring. |
| Cohort | Month of the first valid purchase. Pre-2017 history is used when assigning cohorts, so a 2016 buyer is never mislabelled "new". |
| Retention (M_k) | Share of the cohort with ≥1 valid order in calendar month cohort + k. Cells after Aug 2018 are **NULL (unobservable)**, not 0. |
| Weighted retention | Σ active / Σ cohort size across the cohorts that are observable at k. |
| Recency | Snapshot − last purchase date, in days. |
| Monetary | Lifetime GMV, excluding freight. |
| RFM scores | R and M as quintiles (`NTILE(5)`, ties broken by id). F is capped at 3 because 97.8% of customers have F = 1, which would make quintiles degenerate. |
| High-value | Monetary ≥ 80th percentile (R$179.90). |
| Potentially inactive | Recency > 180 days. **This is not a churn label.** No ground truth exists to validate churn. |
| At-risk (valuable) | (repeat or high-value) **and** 169 < recency ≤ 365 days. 169 days is the 75th percentile of observed gaps between purchases, so 75% of repeat purchases happen sooner. |

### Segments (mutually exclusive, applied in priority order)

1. Frequent: 3+ purchase days
2. Repeat: 2 purchase days
3. High-value one-time: 1 day, monetary ≥ P80
4. New one-time: 1 day, recency ≤ 90
5. One-time cooling: 1 day, recency 91–180
6. One-time potentially inactive: 1 day, recency > 180

## Module C: categories

| Metric | Definition |
|---|---|
| Category GMV | Σ item price by product category (English translation; `unknown` when missing). |
| Category share / cumulative share | Window functions over GMV, ordered descending. |
| Category growth | Jan–Aug 2018 vs Jan–Aug 2017 GMV. |
| Category review / on-time | Computed at **order × category** grain, so a multi-item order counts once per category. This attributes the order-level review to every category in the order, which is a stated simplification. |
| Seller concentration | GMV share of the top 1% / 10% / 20% of sellers. HHI = Σ(share²)·10,000. |

## Module D: experiment (synthetic)

See `experiment_methodology.md`. Primary metric: **contribution profit per eligible customer**.

## Module E: opportunity sizing

Contribution = 15% × GMV − R$1.50 × orders. **Both values are assumptions** shared with Module D, because Olist has no cost data.
