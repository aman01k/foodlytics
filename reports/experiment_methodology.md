# Experiment methodology: 10% discount A/B test (SYNTHETIC)

> **Every experimental outcome in this project is simulated.** The Olist dataset contains no randomized promotion. Historical data is used **only** to calibrate the control arm. The treatment effect and the unit economics are explicit assumptions that you can change in `ExperimentConfig` (or with the dashboard sliders).

Code: `src/experiment_simulator.py` (data generation) and `src/experiment_analysis.py` (statistics, decision, break-even, power). Outputs: `reports/results/experiment_*` and the `analytics.exp_*` tables. Notebook: `notebooks/experiment_analysis.ipynb`.

## 1. Business question

Should the platform offer a **10% discount** to one-time buyers to drive a repeat purchase, and would that produce **incremental contribution profit**, not just more orders?

## 2. Design

| Element | Choice | Rationale |
|---|---|---|
| Eligible population | One-time buyers whose only purchase day was 31–365 days ago (**65,627** real customers at 2018-09-01) | This is the reactivation target. Buyers in the last 30 days are excluded because they are still in their natural repurchase window. Buyers lapsed more than a year are excluded as a different problem. |
| Unit of randomization | Customer | The outcome is measured per customer, and there is no cross-customer interference. |
| Allocation | 50/50, exact split, seeded permutation (`seed = 42`) | This gives maximum power for a fixed n and removes chance imbalance in arm sizes. |
| Control | No promotion | |
| Treatment | 10% off every order placed in the window | |
| Observation window | 60 days | |
| α / power | 0.05 two-sided / 80% target | |

### Pre-registered metrics (fixed before any outcome was generated)

* **Primary:** contribution profit per *eligible* customer. Every assigned customer is in the denominator, converted or not, which is an intention-to-treat analysis.
* **Secondary:** conversion rate (≥1 order in the window).
* **Guardrails:** AOV of converters, and discount cost per eligible customer.

Profit is the primary metric because conversion alone rewards giving money away. A discount that lifts conversion but loses money is a failure.

## 3. Calibration from real data (observed)

| Input | Value | How |
|---|---|---|
| Control conversion | **0.313%** (192 / 61,375) | **Historical back-test.** Apply the same eligibility rule at a past snapshot (2018-07-01) and measure who actually purchased in the next 60 days. |
| Order value distribution | 2,316 real repeat-purchase orders, mean R$125.96 | Bootstrap resampling of actual orders from customers' 2nd and later purchase days. |
| Extra orders per converter | 0.051 | Observed extra purchase days within 60 days of a first repeat. |

## 4. Assumptions (not observable; varied in the sensitivity analysis)

| Parameter | Default | Effect on the conclusion |
|---|---|---|
| Price elasticity of conversion | 1.5 → relative lift = 1.5 × 10% = **15%** | A larger lift helps, but the break-even lift is 263%. |
| Contribution margin on GMV, before promotion | **15%** | Sets how much margin the discount eats. A 10% discount at a 15% margin leaves 5%. |
| Variable cost per order | R$1.50 | A small effect. |
| Basket-size effect of the discount | 0% | You can turn it on with `aov_uplift_treated`. |

Why an elasticity rather than a hand-picked "true lift": tying the lift to the discount size makes the sensitivity grid internally consistent. A deeper discount implies a bigger lift. The elasticity is still a guess, so every conclusion is shown across lifts from 0% to 300%.

## 5. Simulation model

For each synthetic customer (`SIM-xxxxxx`):

1. Assign to an arm.
2. `converted ~ Bernoulli(p)`, where p = p₀ for control and p₀ × (1 + lift) for treatment.
3. `n_orders = 1 + Poisson(0.051)` if the customer converted.
4. GMV = sum of resampled real order values.
5. `discount_cost = 10% × GMV` (treatment only).
6. `contribution = 15% × GMV − 1.50 × n_orders − discount_cost`.

The key economics fall out naturally from this model. **Treated customers who would have bought anyway also receive the discount.** That subsidy is the cost the incremental orders must pay back.

Validation: across 60 seeds, the mean simulated profit difference matches the closed-form expectation (`tests/test_experiment.py::test_simulator_is_unbiased_against_closed_form`).

## 6. Statistical methods

| Metric | Method | Why |
|---|---|---|
| Conversion | Two-proportion z-test (pooled SE). 95% Wald CI on the absolute difference. Delta-method CI on log(p₁/p₀) for the relative lift. | Standard for large-n binary outcomes. The z-statistic is checked against a manual computation in the tests. |
| Contribution and revenue per eligible customer | Welch t-test plus a 1,000-resample bootstrap percentile CI | The data is zero-inflated (99.7% zeros) and heavy-tailed. Welch is valid by the central limit theorem at n ≈ 33k per arm. The bootstrap is a distribution-free check, and the two agree. Mann-Whitney was rejected because it tests distribution shift, not a difference in means, and the business cares about the mean (total profit). |
| AOV of converters | Welch plus bootstrap | Small n (about 110 per arm), so it is reported as a guardrail only. |
| Power and sample size | Cohen's h with `statsmodels` `NormalIndPower`; cross-checked against the classic unpooled formula (within 1%) | |
| Decision stability | Monte Carlo: the full experiment re-run under 200 seeds | This estimates how often each decision would be reached if the assumptions were true. |

## 7. Decision framework (implemented in `decide()`, never hardcoded)

| Outcome | Rule | Action |
|---|---|---|
| **1. Launch** | Profit-difference 95% CI lower bound > 0 | Roll out with a permanent holdout. |
| **2. Conversion up, profit down** | Conversion significantly up **and** profit CI upper bound < 0 | Do not launch as designed. Test a smaller or threshold discount, or target customers whose baseline propensity is low. |
| 2b. Conversion up, profit unresolved | Conversion significantly up, profit CI spans 0 | Do not scale yet. Extend the test to its powered size. |
| **3. No reliable improvement** | Conversion not significant | Do not launch. Re-test only with a design powered for the *profitable* lift. |

## 8. Results with default assumptions (seed 42, SYNTHETIC)

| Metric | Control | Treatment | Difference (95% CI) |
|---|---|---|---|
| Customers | 32,813 | 32,814 | |
| Conversion | 0.314% | 0.347% | +0.034 pp (−0.054 to +0.121); relative +10.7% (−15.2% to +44.4%); **p = 0.455** |
| Net revenue / eligible | R$0.464 | R$0.416 | −R$0.049 (−0.227 to +0.130) |
| Discount cost / eligible | 0 | R$0.046 | |
| **Contribution / eligible** | R$0.065 | R$0.018 | **−R$0.047 (−0.068 to −0.026)**, bootstrap (−0.068 to −0.028), p = 1.2 × 10⁻⁵ |
| Rolled out to all 65,627 | | | −R$3,076 per campaign (simulated). The closed-form expectation is −R$2,562. |

**Computed decision: outcome 3, "No reliable improvement: do not launch", with contribution profit significantly lower.**

Monte Carlo over 200 seeds: outcome 3 in **84%** of runs and outcome 2 in **16%**. **No run** reached "launch". The recommendation does not depend on the seed.

### Break-even analysis (closed form)

Expected contribution per converter: control m·A − c = **R$17.39**; treated (m − d)·A − c = **R$4.80**.
The treatment arm therefore needs p₁/p₀ ≥ 17.39 / 4.80 = 3.63, which is a **+262.5% relative lift**. That means conversion would have to rise from 0.31% to **1.13%**.

The largest discount that still breaks even, for a given true lift (15% margin):

| True relative lift | 5% | 10% | 15% | 25% | 50% | 100% |
|---|---|---|---|---|---|---|
| Break-even discount | 0.7% | 1.3% | **1.8%** | 2.8% | 4.6% | 6.9% |

The relative lift needed to break even, by margin and discount:

| Margin \ discount | 3% | 5% | 10% | 15% | 20% |
|---|---|---|---|---|---|
| 10% | 52% | 131% | impossible | impossible | impossible |
| 15% | 28% | 57% | **263%** | impossible | impossible |
| 20% | 19% | 36% | 114% | 394% | impossible |
| 25% | 14% | 27% | 72% | 170% | 525% |
| 30% | 12% | 21% | 53% | 109% | 227% |

### Power

* Power at 32,813 per arm for the assumed 15% lift: **18%**.
* n per arm needed for 80% power at a 15% lift: **238,651**. That is 7× the whole eligible population.
* Minimum detectable relative lift at the current n: **42.8%**.
* n per arm needed to detect the break-even lift (263%): about 1,525. **A test powered only to detect "profitable or not" is cheap.** Detecting small lifts is what is expensive.

## 9. Limitations

* The treatment effect is assumed. The real elasticity of Brazilian e-commerce customers to a 10% voucher is unknown.
* The margin and costs are assumptions. Olist publishes no take-rate or cost data.
* The model ignores long-term effects (habit formation, discount conditioning), cannibalisation of full-price orders beyond the window, and network or seller effects.
* The baseline comes from one back-test snapshot (2018-07-01, 192 conversions). Its own 95% CI is roughly 0.27%–0.36%.
* Food delivery has much higher purchase frequency, so its baseline conversion and power picture would differ entirely. The **method** transfers; the numbers do not.

## 10. Alternatives considered

* **CUPED / stratification on pre-period spend** would reduce variance. It was not implemented because the synthetic data has no pre-period covariates, but it would be the first improvement in a real test.
* **A Bayesian decision analysis** would report P(profit > 0) and expected loss. That is more natural for a business audience; the frequentist approach was kept because it is the interview standard.
* **Sequential testing** (e.g. alpha-spending) would allow peeking. Not needed here because the analysis is fixed-horizon.
