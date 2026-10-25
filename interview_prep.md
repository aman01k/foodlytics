# Interview preparation: Foodlytics

Every answer here is grounded in what the repo actually does and in numbers it computed. If you're asked about something not listed, say so. Don't extrapolate.

---

## 1. 60-second introduction

> "I built Foodlytics, an end-to-end analytics project answering the questions a food-delivery business team would ask: what drives growth, who comes back, where we lose orders, and whether discounts pay. There is no public Swiggy data, so I used the Olist Brazilian marketplace dataset (100k orders) as a clearly labelled proxy.
>
> I built a reproducible pipeline: Python cleaning, PostgreSQL with raw, clean and analytics schemas, SQL views for every KPI, and 57 automated tests. The analysis showed growth was entirely volume-driven (+137% orders YoY, AOV flat) and that only 2.2% of customers ever return. Late deliveries score 2 stars lower than on-time ones.
>
> I then built a synthetic A/B test simulator, calibrated on a real historical back-test. It showed a blanket 10% discount would need a 263% conversion lift just to break even, so the computed recommendation was not to launch. I recommended a targeted non-discount retention programme instead. Everything is in a Streamlit dashboard that queries the database live."

---

## 2. Architecture

```
Kaggle / HF mirror ──► data/raw (9 CSVs, size-verified, SHA-256 manifest)
        │  src/ingestion.py
        ▼
src/clean_data.py ──► data/processed (typed CSVs + cleaning_report.json)
        │  flag, don't drop; 1 review/order; translate categories; dedupe geo
        ▼
PostgreSQL 16
   raw.*        TEXT copies of source (audit / reconciliation)
   clean.*      PK / FK / CHECK constraints + indexes   (sql/schema.sql)
   analytics.*  fct_orders, dim_customers, KPI views     (sql/analytical_views.sql)
        │
        ├── src/validate_data.py   20 SQL DQ checks (sql/cleaning_and_validation.sql)
        ├── src/metrics.py         36 named business queries → reports/results/*.csv
        ├── src/experiment_*.py    calibration back-test → simulation → stats → decision
        ├── src/opportunity_sizing.py
        └── dashboard/ (Streamlit, 5 pages, parameterized SQL, live simulator)
run_pipeline.py rebuilds everything from scratch in ~45 s; pytest: 57 tests.
```

**Why these choices**

* **Three schemas.** Raw is kept so clean rows can be reconciled against it (a check proves zero business rows were dropped). Analytics views give every consumer one definition of each metric.
* **PostgreSQL rather than pandas only.** SQL is the BA lingua franca. Views are reusable by any BI tool, including Power BI.
* **Streamlit rather than Power BI.** Power BI Desktop is Windows-only and wasn't available on the Mac I built on. The SQL layer is BI-agnostic, so Power BI can connect to the same views.
* **No ML, no cloud.** The questions are descriptive and causal, not predictive, and there was no churn label to train on.

---

## 3. Ten important SQL queries

1. **Order fact without fan-out** (`sql/analytical_views.sql`, `fct_orders`). Items and payments are each aggregated to order grain in separate CTEs, then LEFT JOINed to orders. Joining items × payments first inflates GMV; a test proves the naive join over-counts. *Concepts: grain, CTEs, LEFT JOIN.*
2. **First-order sequencing.** `ROW_NUMBER() OVER (PARTITION BY customer_unique_id, is_valid ORDER BY purchase_ts, order_id)` gives `valid_order_seq`. The tie-breaker on `order_id` makes it deterministic. *Concepts: window functions, determinism.*
3. **Monthly KPIs with MoM growth** (`v_kpi_monthly`). Conditional aggregation (`COUNT(*) FILTER (WHERE is_valid)`), then `gmv / LAG(gmv) OVER (ORDER BY month) − 1`, plus `RANK()` for the busiest months.
4. **GMV decomposition** (`v_gmv_decomposition`). `LAG()` of orders and AOV produces volume, value and interaction effects that sum exactly to ΔGMV.
5. **YoY on comparable months** (`v_yoy_growth`). Aggregate Jan–Aug per year, then self-join 2017 to 2018. This avoids comparing a Black-Friday month with a normal one.
6. **Cohort retention with censoring** (`v_cohort_retention`). Cohort = first purchase month. `GENERATE_SERIES(0,19)` builds the full grid, and cells after the last complete month are set to NULL rather than 0. *Concepts: CROSS JOIN grid, LEFT JOIN, month arithmetic.*
7. **Repeat within N days, right-censored** (`v_repeat_within_days`). A 2nd distinct purchase day comes from `ROW_NUMBER() = 2`. Only customers whose first purchase + N days falls before the data end are kept. `COALESCE(..., FALSE)` stops non-repeaters from silently dropping out of `AVG`, which was a real bug I caught.
8. **RFM and segmentation** (`dim_customers`). `NTILE(5)` for R and M, F capped at 3, a P80 threshold via `PERCENTILE_CONT`, and a priority `CASE` for mutually exclusive segments.
9. **Seller concentration** (`v_seller_concentration`). `ROW_NUMBER()` by GMV, then `SUM(share) FILTER (WHERE rnk <= CEIL(n*0.10))` for the top-10% share, and HHI = Σshare²×10,000.
10. **Delivery vs review** (`v_delivery_vs_review`). Bucket `delivered_date − estimated_date` with `CASE`, then aggregate average review and 1–2★ share. Grouping by a derived bucket is the dose-response view.

Bonus: `src/experiment_simulator.py` holds the **back-test calibration query**. It applies the eligibility rule at a past snapshot and measures actual 60-day conversion. This is the historical "control group".

---

## 4. Ten business-analysis questions

**Q1. Is the business growing?**
Yes, by volume only. Jan–Aug orders rose +137% YoY and GMV +138%, while AOV moved +0.4%. But 2018 monthly orders fell 10.7% from January to August, so growth is plateauing.

**Q2. Is growth driven by volume or value?**
Volume. It explains 76% of absolute monthly GMV movement, and corr(ΔGMV, volume effect) is 0.96 versus 0.13 for value.

**Q3. What percentage of customers return?**
2.17% buy on two or more distinct days. Counting orders instead would give 3.04%, but 823 of those "repeaters" only split one basket into several orders on the same day.

**Q4. How long until a second order?**
The median gap is 69 days and P75 is 169. Only 1.31% of new customers repeat within 90 days.

**Q5. Which segments deserve retention campaigns?**
High-value one-time buyers (19% of customers, 53.5% of GMV) and the 7,928 at-risk valuable customers: repeat or high-value customers silent longer than 169 days, the P75 gap. Not the 45k potentially inactive low-value one-timers, because spend there is unlikely to pay back.

**Q6. Where are cancellations concentrated?**
68% happen after approval but before carrier handover, which is the seller-fulfilment stage. That points to seller operations, not demand.

**Q7. Do delays hurt reviews?**
Strongly associated: 4.29★ on time vs 2.27★ late, a 95% CI on the difference of 1.98–2.06, and 79% 1–2★ when more than 8 days late. There is a dose-response pattern and time co-movement (Feb–Mar 2018), but it is not proven causal.

**Q8. Which categories matter most?**
18 of 74 make up 80% of GMV. The top 5 are health_beauty, watches_gifts, bed_bath_table, sports_leisure and computers_accessories. The risk is bed_bath_table: #3 by GMV but 3.97★.

**Q9. What is the biggest opportunity?**
Retention. +1 pp on the 12-month repeat rate is worth about R$103k GMV a year, more than the cancellation and delivery levers combined. Even so it is small (1% of LTM GMV), because the base repeat rate is tiny. I state that honestly.

**Q10. What should management prioritise?**
(1) Targeted non-discount retention with a holdout. (2) No blanket discounts. (3) Seller SLAs. (4) Delivery promise reliability. (5) Investigate the acquisition plateau.

---

## 5. A/B testing and statistics

**Q1. Why is contribution per eligible customer the primary metric, not conversion?**
Conversion rewards giving money away. Every treated customer who would have bought anyway still gets 10% off, and that subsidy has to be paid back by incremental orders. Using *all* eligible customers in the denominator is intention-to-treat, which keeps randomization valid.

**Q2. Which tests did you use and why?**
- Conversion: a two-proportion z-test, plus a Wald CI on the difference and a delta-method CI on the relative lift.
- Profit per customer, which is 99.7% zeros and heavy-tailed: a Welch t-test (valid by the CLT at n ≈ 33k per arm), with a bootstrap percentile CI as a distribution-free check. They agree.
- I rejected Mann-Whitney because it tests distribution shift, not the mean, and the business needs total profit.

**Q3. Your simulated lift was +10.7% but not significant. What does that mean?**
At 32.8k customers per arm with a 0.31% baseline, power for a 15% lift is only 18%. Detecting that lift needs about 239k per arm, 7× the eligible population. But the business question is "is it profitable?", and break-even needs a +263% lift. Detecting that needs only about 1,525 per arm. **Design the test for the decision, not for a vanity metric.**

**Q4. How did you avoid making up the treatment effect?**
The control arm comes from a real back-test: 192 of 61,375 eligible buyers converted within 60 days. Order values are resampled from 2,316 real repeat orders. The treatment effect is an explicit elasticity assumption (lift = 1.5 × discount), varied from 0% to 300% in the sensitivity analysis. The decision function is code, so changing assumptions changes the decision. A test also confirms the simulator is unbiased against the closed-form expectation.

**Q5. How did you compute break-even?**
Expected contribution per converter is m·A − c for control (R$17.39) and (m − d)·A − c for treatment (R$4.80). Profit is equal when p₁/p₀ = 17.39 / 4.80 = 3.63, i.e. +263%. Inverting the same equation gives the maximum affordable discount for a given lift: 1.8% at a 15% lift.

---

## 6. Data quality and metric definitions

**Q1. How do you define a customer?**
`customer_unique_id`. Olist's `customer_id` is generated per order: 99,441 ids for 96,096 unique accounts. Using `customer_id` would make the repeat rate exactly 0%. Even `customer_unique_id` is an account proxy, not a verified person.

**Q2. How did you avoid double-counting revenue?**
Each table is aggregated to order grain before joining. Automated checks confirm Σ order GMV = Σ item price and Σ order payments = Σ payment rows, and a test shows the naive join over-counts.

**Q3. GMV vs payment value vs revenue?**
- GMV is item price (R$13.45M).
- Payment value includes freight, installment interest and vouchers (R$15.69M for valid orders).
- Olist's revenue and profit are not observable. Any profit figure here is a labelled assumption (15% margin).

**Q4. What did cleaning find, and what did you drop?**
- No PK duplicates and no orphan foreign keys.
- 1,396 orders with timestamp anomalies, **flagged, not dropped**. Metrics that depend on bad timestamps are set to NULL.
- 775 orders without items.
- 551 superseded reviews: kept the latest per order.
- 261,831 duplicate geolocation rows.
- 610 products with no category, set to `unknown`.
A reconciliation check proves zero order, item, payment or customer rows were lost.

**Q5. Why exclude 2016 and Sep–Oct 2018?**
2016 has 329 orders and a missing month (platform ramp-up). Sep–Oct 2018 has 20 orders (data cut-off). Including them creates fake growth and fake collapse in monthly rates. Customer history still uses 2016, so nobody is wrongly labelled "new".

---

## 7. Three hard questions about limitations and mistakes

**Q1. "Isn't this just e-commerce? How is it relevant to food delivery?"**
Yes, and I say so throughout. The *methods* transfer: grain-safe revenue modelling, cohort retention with censoring, distinct-occasion frequency, profit-first experiment design, and break-even thinking. The *numbers* don't. Food delivery has weekly frequency, so baseline conversion is far higher, tests need far smaller samples, and retention is the core business rather than a side lever.

**Q2. "You claim late delivery hurts retention. How do you know it's causal?"**
I don't claim it. I report an association (repeat 3.03% vs 1.75%), size it as an explicit *upper bound* (≤ R$3.9k GMV a year), and propose a randomized promise-date experiment. Confounders include region, product size and seller quality.

**Q3. "What mistakes did you catch in your own analysis?"**
Three of them:
1. My first repeat-within-N-days view returned 29% at 30 days. `AVG` was ignoring NULLs for customers with no second purchase. After a `COALESCE(..., FALSE)` fix, the correct figure is 0.67%.
2. The experiment results changed between database rebuilds because the calibration query had no `ORDER BY`. Seeded resampling then drew from a different row order. I added deterministic ordering and tie-breakers on all `NTILE` and `ARRAY_AGG` calls, and verified bit-identical results across rebuilds.
3. Counting orders instead of purchase days would have overstated the repeat rate by 40%.

---

## 8. Walkthrough: the key recommendation

**Recommendation: don't buy retention with blanket discounts. Run a targeted, non-discount retention programme with a holdout.**

1. **Problem.** Growth is volume-only and plateauing (−10.7% Jan → Aug 2018). Only 2.17% of customers return, so growth depends entirely on acquisition.
2. **Where the value is.** High-value one-time buyers are 19% of customers and 53.5% of GMV. 7,928 valuable customers are past the P75 repurchase gap.
3. **The obvious lever fails.** A 10% discount must lift conversion 263% to break even. The calibrated simulation gives −R$0.047 per eligible customer, and none of 200 Monte Carlo runs reaches "launch".
4. **Size of the prize.** Each +1 pp of 12-month repeat is about R$103k GMV a year [scenario]. That is modest, so the programme must be cheap: non-monetary nudges timed to the 69-day median gap, plus fixing first-order experience (on-time, well-rated first orders are associated with 1.7× higher repeat).
5. **Measurement.** A randomized holdout with a 90-day repeat-rate primary metric and contribution as a guardrail. Re-evaluate at 365 days.
6. **What would change my mind.** Real promotion data showing much higher responsiveness, or better margins. From the break-even table: at a 25% margin, a 5% discount breaks even at a +27% lift. At our assumed 15% margin, even a 3% discount needs +28%. If a real test showed lifts that large, small targeted discounts would become profitable.
