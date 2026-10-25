# Analysis findings: Modules A–C

Every number below comes from executed queries. The outputs are in `reports/results/*.csv`, and the file prefix (a01…, b01…, c01…) maps each finding to its named query in `sql/*.sql`. Window: Jan 2017 – Aug 2018 unless stated.

---

## Module A: Revenue and business performance

### A1. Is the business growing?

* **Question:** Is the business growing or declining, and what drives it?
* **Metric:** valid orders, GMV and AOV. Year-over-year on comparable months (Jan–Aug), plus a monthly GMV decomposition.
* **Method:** `v_yoy_growth` uses conditional aggregation. `v_gmv_decomposition` uses `LAG()` window functions (ΔGMV = volume + value + interaction effects).
* **Why this method:** YoY on matched months removes seasonality, notably the Black Friday spike in Nov 2017. The decomposition separates "more orders" from "bigger orders".
* **Result:**
  * Jan–Aug 2018 vs 2017: orders **22,562 → 53,530 (+137%)**, GMV **R$3.08M → R$7.34M (+138%)**, AOV **R$136.55 → R$137.14 (+0.4%)**.
  * Volume explains **76%** of absolute month-on-month GMV movement. corr(ΔGMV, volume effect) = 0.96 vs 0.13 for value.
  * Highest-volume months: Nov 2017 (7,421 valid orders, Black Friday), Jan 2018 (7,187), Mar 2018 (7,168).
  * **2018 is a plateau:** monthly orders fell from 7,187 in Jan to 6,421 in Aug (−10.7%).
* **Implication:** growth came from acquiring customers, not from basket size or frequency. The 2018 flattening means the acquisition engine is slowing, and nothing else is growing to replace it.
* **Limitations:** no traffic, marketing-spend or seller-onboarding data, so the cause of the plateau cannot be identified.
* **Alternatives:** a log-change decomposition gives exact additivity without an interaction term. A seasonal decomposition (STL) needs more years of data than exist here.

### A2. Headline KPIs (`a01_kpi_summary`)

| KPI | Value |
|---|---|
| Orders placed | 99,092 |
| Valid / delivered | 97,905 / 96,211 |
| GMV (item price) | **R$13.45M** |
| Freight | R$2.23M |
| Payment value (valid orders) | R$15.69M |
| AOV | **R$137.37** (R$160.19 incl. freight) |
| Items per order | 1.14 |
| Cancellation rate / failed-order rate | **0.59% / 1.19%** |
| Approval time / carrier handover | 10.3 h / 3.2 days |
| Delivery time (median / mean) | 10.2 / 12.5 days |
| On-time delivery (vs promised date) | **93.2%** |
| Average review | 4.09 |

### A3. Where are cancellations concentrated? (`a07`–`a10`)

* **68% of cancellations (394 of 580)** happen after payment approval but before carrier handover. That is the seller-fulfilment stage. 116 happen before approval (payment issues) and 70 after handover.
* There are 602 `unavailable` orders (stock-outs). They carry no item data, so their value can only be estimated with AOV.
* Among large states, SP has the highest failed-order rate (1.44%). Among categories with ≥500 orders, books, musical instruments and small appliances have the highest cancel rates, at 1.3–1.4%.
* **Implication:** cancellations are mainly a **seller operations** problem, not a customer-demand problem.
* **Limitation:** recent orders can still be canceled after the data snapshot, so the Aug 2018 spike (1.29%) may be partly an artefact of the data cut-off. No cancellation reason codes are available.

### A4. Delivery delays and review scores (`a11`, `a12`)

| Delivery vs promise | Orders | Avg review | 1–2★ share |
|---|---|---|---|
| 10+ days early | 61,270 | 4.32 | 8.9% |
| 1–9 days early | 26,632 | 4.23 | 10.0% |
| On the estimate day | 1,280 | 4.03 | 12.4% |
| 1–3 days late | 1,851 | 3.29 | 32.1% |
| 4–7 days late | 1,748 | 2.10 | 67.7% |
| 8+ days late | 2,779 | **1.70** | **79.3%** |

* On-time orders average **4.29★** and late orders **2.27★**. The difference is 2.02 (95% CI 1.98–2.06), with Welch t = 100.8.
* The months with the worst on-time rates, Feb 2018 (85.9%) and Mar 2018 (81.0%), also had the lowest average reviews (3.83 and 3.75).
* **Correlation, not causation.** Late orders may differ in other ways: region, product size, seller quality. The dose-response pattern and the time-series co-movement make a causal link plausible, but only an experiment, for example on promise-date buffering, can confirm it.

### A5. Geography (`a14`)

SP accounts for 38.3% of GMV, with an 8.7-day average delivery. North and Northeast states take 18–30 days, and AL has a 78.5% on-time rate. RJ is #2 by GMV (13.4%) but has a low on-time rate (87.9%) and a 3.91 average review. That makes RJ the largest single pocket of delivery risk.

---

## Module B: Customer retention

### B1. How many customers return? (`b01`, `b02`, `b07`)

* There are 94,983 customers. **Only 2,063 (2.17%) purchased on two or more distinct days.**
* An order-based definition would give 3.04%. The difference is 823 customers who placed several orders on the same day, which are split baskets, not loyalty. Definition choice changes the headline by 40%.
* Repeat within 30 / 60 / 90 / 180 / 365 days of the first purchase: **0.67% / 1.03% / 1.31% / 1.99% / 3.34%**. Only customers with a full window are counted.
* Repeat customers generate 4.2% of GMV, with lifetime GMV of R$271.86 vs R$139.19 for one-time customers.

### B2. Cohorts (`b04`–`b06`)

* Size-weighted retention is **M1 0.48%, M3 0.26%, M6 0.23%, M12 0.18%**. Retention is flat after M3, which suggests a small core of habitual buyers.
* Cumulative M1–3 repeat by cohort ranges from 0.65% (Feb 2017) to 1.45% (Sep 2017). The spread is narrow and no cohort shows retention improving over time.
* The share of returning customers among monthly actives rose from 0.1% to about 3%. This is mechanical: the pool of past customers grows. It does not mean retention is improving.

### B3. Time between purchases (`b08`, `b09`)

The median gap is **69 days**, P75 is 169 and P90 is 281. 30% of repeat purchases happen within 30 days and 56% within 90 days. These percentiles set the at-risk threshold (169 days), which is derived from data rather than invented.

### B4. Segments (`b10`)

| Segment | Customers | % customers | % GMV | Avg GMV |
|---|---|---|---|---|
| Frequent (3+ days) | 156 | 0.16% | 0.51% | R$440.63 |
| Repeat (2 days) | 1,907 | 2.01% | 3.65% | R$258.05 |
| **High-value one-time** | **18,067** | **19.0%** | **53.5%** | R$399.92 |
| New one-time (≤90d) | 14,360 | 15.1% | 8.1% | R$76.26 |
| One-time cooling (91–180d) | 15,460 | 16.3% | 8.9% | R$77.92 |
| One-time potentially inactive (>180d) | 45,033 | 47.4% | 25.3% | R$75.69 |

* **At-risk valuable customers:** 7,928 repeat or high-value customers silent for 169–365 days, with R$3.0M of historical GMV (`b12`).
* In the RFM grid (`b11`), the most recent and highest-spend quintile repeats at 8.6% vs 0.2% for the lowest. Part of this is mechanical, because repeaters accumulate more GMV.
* First experience (`b13`, cohorts with ≥180 days observed): repeat rate is **3.03%** after an on-time, 4–5★ first order vs **1.75%** after a late, 1–2★ one. This is an association.

### B5. What prevents confident churn prediction?

* There is no churn ground truth (no account closures or unsubscribes), and purchase intervals are long and irregular.
* 97.8% of customers have exactly one purchase, so there are almost no positive "returned" labels per customer.
* The observation window is only 20 months. Customer identity is an account proxy.
* There are no engagement signals (sessions, app opens, notifications). That is why the project uses rule-based "potentially inactive" labels instead of a churn model.

---

## Module C: Product and category performance

### C1. Concentration and ranking (`c01`, `c02`, `c05`)

* 74 categories. **18 categories make up 80% of GMV.** The top 5 are health_beauty (9.3%), watches_gifts (8.9%), bed_bath_table (7.7%), sports_leisure (7.3%) and computers_accessories (6.7%).
* Seller concentration: the top 1% of 3,029 sellers earn 26.2% of GMV, the top 10% earn 67.4% and the top 20% earn 82.5%. HHI is 36, which is unconcentrated at platform level. The median seller has only 7 orders.

### C2. Growth leaders and laggards (`c03`; Jan–Aug YoY, categories ≥1% share, platform +138%)

* **Fastest:** baby (+264%), stationery (+263%), watches_gifts (+243%) and electronics (+241%). construction_tools grew 3,441% from a tiny base.
* **Slowest:** cool_stuff (+9%), luggage (+25%), small_appliances (+32%), consoles_games (+36%) and toys (+42%). These are losing share in a market growing 138%.

### C3. Quality risks (`c04`, `c06`)

* **office_furniture** has the lowest review (3.63★), 22.4% 1–2★ reviews and 20.5-day deliveries. **63.5% of its GMV comes from a single seller.** This is quality risk and dependency risk at once.
* **bed_bath_table** is #3 by GMV (7.7%) yet averages 3.97★ with 16.7% 1–2★ reviews. It is a high-revenue category with a weak experience.
* watches_gifts depends on its top 3 sellers for 46.6% of GMV, and perfumery for 44.0%.

### C4. Price mix (`c08`)

Items priced at R$200 or more are 12% of items but **44% of GMV**. Reviews are flat across price bands (4.03–4.07), so price does not explain dissatisfaction; delivery does.

### Category insights (actionable)

1. **Protect the high-GMV, low-satisfaction categories** (bed_bath_table, furniture_decor). They carry 13% of GMV and have the worst review profiles among large categories.
2. **De-risk office_furniture.** Onboard additional sellers to reduce the 63.5% single-seller dependency and the 20.5-day delivery time.
3. **Double down on breakout categories.** baby, stationery and watches_gifts are each growing faster than 240%, for example through seller acquisition and merchandising.
4. **Diagnose the laggards.** cool_stuff and toys are losing share. Check whether the cause is seller supply or demand.
5. Category reviews and on-time rates are confounded by product size and seller location. **Recommended further analysis:** a seller-level model of review score on delay, category, distance and seller fixed effects, to separate category effects from logistics effects.
