# Executive summary: Foodlytics

**Data:** Olist Brazilian e-commerce marketplace, Jan 2017 – Aug 2018. That is 99k orders, 95k customers and R$13.45M GMV. It is a **proxy** for a food-delivery platform, not food-delivery data.
**Labels:** [Observed] = computed from data · [Scenario] = assumption-based estimate · [Simulated] = synthetic experiment.

## 1. Most important findings

1. **Growth is entirely volume-driven, and it has stalled.** [Observed]
   * Orders grew 137% YoY (Jan–Aug 2018 vs 2017) while AOV moved only 0.4%.
   * Volume explains 76% of month-to-month GMV movement.
   * Monthly orders have drifted down 10.7% since Jan 2018.
2. **Customers almost never come back.** [Observed]
   * 2.17% of customers buy on a second day.
   * 3.34% return within a year.
   * Cohort retention is about 0.5% at M1 and 0.2% by M12.
   * High-value one-time buyers (19% of customers) hold 53.5% of GMV.
3. **Late delivery is the clearest experience failure.** [Observed]
   * Late orders average 2.27★ vs 4.29★ on time, and 79% of orders more than 8 days late get 1–2★.
   * On-time dropped to 81% in Mar 2018. RJ (13% of GMV) runs at 88% on time.
   * This is an association, not a proven cause.
4. **Cancellations are a seller-operations problem.** [Observed]
   * 68% happen after payment approval but before handover to the carrier.
   * The overall failed-order rate is 1.19%.
5. **Category risk is concentrated.** [Observed]
   * 18 of 74 categories make 80% of GMV.
   * bed_bath_table (#3 by GMV) has weak reviews.
   * office_furniture depends on one seller for 63.5% of its GMV.
6. **A blanket 10% discount would lose money.** [Simulated]
   * The baseline reactivation rate is 0.31% (observed back-test).
   * The discount must lift conversion by 263% just to break even at a 15% margin.
   * The simulated test shows profit −R$0.047 per eligible customer (95% CI −0.068 to −0.026). The computed decision is "do not launch".

## 2. Most promising opportunities (annual, last-12-month base) [Scenario]

| Opportunity | Base scenario | Δ GMV / yr | Δ contribution / yr |
|---|---|---|---|
| Repeat rate +1 pp (3.34% → 4.34%) | 728 extra repeat customers | **R$103k** | R$14k |
| Recover 25% of failed orders | 194 orders | R$27k | R$3.7k |
| Halve late first deliveries (upper bound, repeat channel only) | 28 extra repeaters | R$3.9k | R$0.5k |
| Avoid a blanket 10% discount [Simulated] | 65,627 eligible | — | ~R$2.6k expected loss avoided per campaign |

## 3. What management should do next

1. Launch a **non-discount retention programme** aimed at high-value one-time and at-risk customers (7,928 identified), with a randomized holdout.
2. **Do not run blanket discounts.** Any discount test should use ≤5% or threshold offers and be sized with the power calculator.
3. Introduce **seller SLAs and a seller scorecard** for cancellations and stock-outs.
4. **Fix delivery promises** in RJ and the Northeast, justified by ratings and experience rather than short-term revenue.
5. **Investigate the 2018 acquisition plateau.** It is the largest driver of the business and the least explained.

## 4. How to measure

Every action has a randomized or quasi-experimental design. Primary metrics: 90-day repeat rate, contribution per eligible customer, failed-order rate by seller, and on-time rate with review score. Details are in `business_recommendations.md` and `opportunity_sizing.csv`.

## 5. Evidence still missing

Unit economics (take rate and costs), marketing spend and traffic, promotion history (real elasticity), cancellation reasons, verified customer identity, and engagement data. Until these exist, profit figures are scenario-based and the experiment results are illustrative.
