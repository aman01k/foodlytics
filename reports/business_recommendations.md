# Business recommendations

Labels used below:
- **[Observed]**: computed from Olist data.
- **[Scenario]**: an assumption-based estimate.
- **[Simulated]**: from the synthetic experiment.

Contribution figures use the assumed 15% margin and R$1.50 per-order cost, because Olist has no cost data.

## Priority 1: Build a targeted, non-discount retention programme for high-value one-time buyers

**Evidence**
* [Observed] Only 2.17% of customers ever return on a second day. The 365-day repeat rate is 3.34%.
* [Observed] High-value one-time customers are 19% of customers but **53.5% of GMV**. 7,928 valuable customers are past the 75th-percentile repurchase gap (169 days) but within a year of their last purchase.
* [Observed] Repeat rate is 3.03% after an on-time, 4–5★ first order vs 1.75% after a late, 1–2★ one. This is an association.
* [Scenario] Each +1 pp on the 12-month repeat rate across 72,760 new customers a year is worth about **R$103k GMV** and about R$14k contribution per year. The range across +0.5 to +2 pp is R$51k–206k GMV.

**Action:** trigger personalised, non-monetary nudges (post-delivery follow-up, recommendations in the purchased category, reminders timed to the 69-day median gap). Start with the at-risk list.

**Measurement:** a randomized holdout of 10–20% of eligible customers. Primary metric: 90-day repeat rate. Read again at 365 days.

## Priority 2: Do not launch a blanket 10% discount

**Evidence [Simulated, calibrated on an observed back-test]**
* Baseline 60-day reactivation for eligible one-time buyers is **0.313%** (observed back-test).
* With an assumed 15% lift, the simulated test shows conversion +10.7% (p = 0.45, not significant) and contribution **−R$0.047 per eligible customer** (95% CI −0.068 to −0.026).
* Computed decision: outcome 3, no reliable improvement, with profit significantly lower. 84% of 200 Monte Carlo runs end in outcome 3; none reach "launch".
* **Break-even requires a +263% relative lift** (0.31% → 1.13% conversion) at a 15% margin. At a realistic 15% lift, the most the business could afford is a **1.8% discount**.

**Action:** if discounts are tested, use small (3–5%) or minimum-basket offers aimed at low-propensity segments. Size the test with the power calculator: 238,651 customers per arm for a 15% lift. Alternatively, design the test to detect only the profitable lift, which needs about 1,525 customers per arm.

## Priority 3: Cut seller-stage cancellations and stock-outs

**Evidence**
* [Observed] 68% of cancellations happen after approval but before carrier handover.
* [Observed] 602 unavailable orders. The failed-order rate is 1.19% (1.02% over the last 12 months).
* [Scenario] Recovering 25% of last-12-month failed orders is worth about R$27k GMV a year.

**Action:** seller SLA monitoring, stock-sync requirements, and a seller scorecard covering cancel and unavailable rates.

**Measurement:** a weekly failed-order rate by seller. Compare pilot sellers with matched controls using difference-in-differences.

## Priority 4: Make delivery promises reliable, starting with RJ and the Northeast

**Evidence**
* [Observed] Late orders average 2.27★ vs 4.29★ on time. 79% of orders more than 8 days late get 1–2★.
* [Observed] On-time fell to 81–86% in Feb–Mar 2018, and reviews dropped with it.
* [Observed] RJ, at 13.4% of GMV, has an 87.9% on-time rate.
* [Scenario, upper bound] Even if the late-vs-on-time repeat gap were fully causal, halving late first deliveries adds only about R$4k GMV a year through repeat purchases.

**Action:** the value case is customer experience and ratings, **not** short-term repeat revenue, and the business case should be honest about that. Buffer estimated delivery dates where carriers under-perform, and add carrier capacity before peaks.

**Measurement:** randomize promise-date buffering by region. Measure on-time rate, review score and 180-day repeat.

## Priority 5: Category portfolio actions

* [Observed] Fix experience in bed_bath_table and furniture_decor. Together they are 13% of GMV, at 3.97–4.02★ with 16–17% 1–2★ reviews.
* [Observed] De-risk office_furniture: one seller holds 63.5% of its GMV, reviews average 3.63★, and delivery takes 20.5 days.
* [Observed] Invest in breakout categories (baby, stationery, watches_gifts, each growing more than 240% YoY). Diagnose share loss in cool_stuff (+9%) and toys (+42%) against a platform growing 138%.

## Strategic note

[Observed] The business is **acquisition-led**: 2018 order volume is flat to declining (−10.7% Jan → Aug), and AOV is flat. Because retention is so low, every retention lever above is small in absolute terms today, but they compound. The most valuable next analysis is the cause of the 2018 acquisition plateau. That needs marketing-spend, traffic and seller-supply data, none of which this dataset contains.

## Evidence missing before acting

1. Unit economics: take rate, payment, logistics and support costs. This changes every profit number.
2. Marketing spend and channel attribution, to explain the acquisition plateau.
3. Promotion history, to get real price elasticity instead of an assumed one.
4. Cancellation reason codes and stock data.
5. Verified customer identity (cross-device, cross-account).
6. Engagement data (sessions, notifications), which is needed for any churn model.
