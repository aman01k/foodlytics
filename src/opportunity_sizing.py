"""Module E - opportunity sizing (scenario analysis, NOT forecasts).

Every baseline is observed in Olist; every target is a scenario assumption.
Contribution profit uses the SAME assumed unit economics as the experiment
(contribution margin on GMV, variable cost per order) because Olist has no
cost data. Annual figures use the last 12 complete months (Sep 2017 - Aug 2018).
"""
from __future__ import annotations

import json

import pandas as pd

from config.settings import RESULTS_DIR
from src.db import query
from src.experiment_simulator import ExperimentConfig

LTM_START, LTM_END = "2017-09-01", "2018-09-01"

BASELINE_SQL = {
    "ltm": f"""
        SELECT COUNT(*)                                        AS orders,
               COUNT(*) FILTER (WHERE is_valid)                AS valid_orders,
               COUNT(*) FILTER (WHERE is_canceled)             AS canceled,
               COUNT(*) FILTER (WHERE is_unavailable)          AS unavailable,
               SUM(gmv) FILTER (WHERE is_valid)                AS gmv,
               AVG(gmv) FILTER (WHERE is_valid)                AS aov,
               SUM(gmv) FILTER (WHERE is_canceled)             AS canceled_gmv_observed,
               COUNT(*) FILTER (WHERE is_canceled AND has_items) AS canceled_with_items,
               COUNT(*) FILTER (WHERE is_delivered AND is_on_time IS NOT NULL) AS delivered_measured,
               COUNT(*) FILTER (WHERE is_on_time = FALSE)      AS late_orders
        FROM analytics.fct_orders
        WHERE purchase_ts >= '{LTM_START}' AND purchase_ts < '{LTM_END}'""",
    "new_customers_ltm": f"""
        SELECT COUNT(*) AS n FROM analytics.dim_customers
        WHERE cohort_month >= '{LTM_START}' AND cohort_month < '{LTM_END}'""",
    "late_first_orders_ltm": f"""
        SELECT COUNT(*) FILTER (WHERE first_on_time = FALSE) AS late_first,
               COUNT(*) FILTER (WHERE first_on_time IS NOT NULL) AS measured_first
        FROM analytics.dim_customers
        WHERE cohort_month >= '{LTM_START}' AND cohort_month < '{LTM_END}'""",
    "repeat_365": "SELECT repeat_rate FROM analytics.v_repeat_within_days WHERE horizon_days = 365",
    "repeat_value": """
        WITH f AS (
            SELECT f.customer_unique_id, f.gmv
            FROM analytics.fct_orders f JOIN analytics.dim_customers c USING (customer_unique_id), analytics.params p
            WHERE f.is_valid AND f.purchase_ts < p.window_end
              AND f.purchase_ts::date > c.first_purchase_ts::date)
        SELECT SUM(gmv) / COUNT(DISTINCT customer_unique_id) AS repeat_gmv_per_repeater,
               COUNT(*)::numeric / COUNT(DISTINCT customer_unique_id) AS repeat_orders_per_repeater
        FROM f""",
    # repeat rate by first-delivery experience, cohorts with >=180 days to observe
    "repeat_by_first_delivery": """
        SELECT first_on_time, COUNT(*) AS customers, AVG(is_repeat::int) AS repeat_rate
        FROM analytics.dim_customers c, analytics.params p
        WHERE c.first_purchase_ts < p.window_end - 180 AND first_on_time IS NOT NULL
        GROUP BY 1""",
}


def baselines() -> dict:
    b = {k: query(v) for k, v in BASELINE_SQL.items()}
    ltm = b["ltm"].iloc[0]
    rv = b["repeat_value"].iloc[0]
    fd = b["repeat_by_first_delivery"].set_index("first_on_time")
    return {
        "ltm_orders": int(ltm.orders), "ltm_valid_orders": int(ltm.valid_orders),
        "ltm_gmv": float(ltm.gmv), "ltm_aov": float(ltm.aov),
        "ltm_canceled": int(ltm.canceled), "ltm_unavailable": int(ltm.unavailable),
        "ltm_canceled_gmv_observed": float(ltm.canceled_gmv_observed or 0),
        "ltm_canceled_with_items": int(ltm.canceled_with_items),
        "ltm_failed_rate": float((ltm.canceled + ltm.unavailable) / ltm.orders),
        "ltm_late_orders": int(ltm.late_orders), "ltm_delivered_measured": int(ltm.delivered_measured),
        "ltm_late_rate": float(ltm.late_orders / ltm.delivered_measured),
        "ltm_new_customers": int(b["new_customers_ltm"].n.iloc[0]),
        "ltm_late_first_orders": int(b["late_first_orders_ltm"].late_first.iloc[0]),
        "repeat_rate_365d": float(b["repeat_365"].repeat_rate.iloc[0]),
        "repeat_gmv_per_repeater": float(rv.repeat_gmv_per_repeater),
        "repeat_orders_per_repeater": float(rv.repeat_orders_per_repeater),
        "repeat_rate_first_on_time": float(fd.loc[True, "repeat_rate"]),
        "repeat_rate_first_late": float(fd.loc[False, "repeat_rate"]),
    }


def contribution(gmv: float, orders: float, cfg: ExperimentConfig) -> float:
    return cfg.contribution_margin * gmv - cfg.variable_cost_per_order * orders


def size(b: dict, cfg: ExperimentConfig | None = None) -> pd.DataFrame:
    cfg = cfg or ExperimentConfig()
    rows = []

    # 1. Repeat purchase rate: +x pp on the 365-day repeat rate of a year's new customers
    for label, pp in [("low", 0.005), ("base", 0.01), ("high", 0.02)]:
        extra = b["ltm_new_customers"] * pp
        gmv = extra * b["repeat_gmv_per_repeater"]
        orders = extra * b["repeat_orders_per_repeater"]
        rows.append({"opportunity": "1. Improve 12-month repeat rate", "scenario": label,
                     "baseline_metric": f"365-day repeat rate {b['repeat_rate_365d']:.2%}",
                     "scenario_assumption": f"+{pp*100:.1f} pp (to {b['repeat_rate_365d']+pp:.2%})",
                     "population": f"{b['ltm_new_customers']:,} new customers / yr",
                     "affected_units": extra, "incremental_gmv": gmv,
                     "incremental_contribution": contribution(gmv, orders, cfg),
                     "evidence_type": "observed baseline + scenario"})

    # 2. Failed orders (canceled + unavailable): recover a share of them
    failed = b["ltm_canceled"] + b["ltm_unavailable"]
    for label, red in [("low", 0.10), ("base", 0.25), ("high", 0.50)]:
        recovered = failed * red
        gmv = recovered * b["ltm_aov"]          # AOV proxy: unavailable orders have no items
        rows.append({"opportunity": "2. Reduce canceled/unavailable orders", "scenario": label,
                     "baseline_metric": f"failed-order rate {b['ltm_failed_rate']:.2%} ({failed:,} orders)",
                     "scenario_assumption": f"{red:.0%} of failed orders converted to completed",
                     "population": f"{b['ltm_orders']:,} orders / yr",
                     "affected_units": recovered, "incremental_gmv": gmv,
                     "incremental_contribution": contribution(gmv, recovered, cfg),
                     "evidence_type": "observed baseline + scenario"})

    # 3. Late first deliveries: UPPER BOUND assuming the observed repeat gap is causal
    gap = b["repeat_rate_first_on_time"] - b["repeat_rate_first_late"]
    for label, red in [("low", 0.25), ("base", 0.50), ("high", 1.00)]:
        fixed = b["ltm_late_first_orders"] * red
        extra = fixed * gap
        gmv = extra * b["repeat_gmv_per_repeater"]
        orders = extra * b["repeat_orders_per_repeater"]
        rows.append({"opportunity": "3. Cut late first deliveries (upper bound)", "scenario": label,
                     "baseline_metric": (f"late rate {b['ltm_late_rate']:.1%}; repeat {b['repeat_rate_first_late']:.2%} "
                                         f"late vs {b['repeat_rate_first_on_time']:.2%} on-time"),
                     "scenario_assumption": f"{red:.0%} of late first orders made on-time; gap treated as causal",
                     "population": f"{b['ltm_late_first_orders']:,} late first orders / yr",
                     "affected_units": extra, "incremental_gmv": gmv,
                     "incremental_contribution": contribution(gmv, orders, cfg),
                     "evidence_type": "observed association -> causal assumption (upper bound)"})
    out = pd.DataFrame(rows)
    out["gmv_pct_of_ltm"] = out.incremental_gmv / b["ltm_gmv"]
    return out


def discount_avoidance(exp_results_path=RESULTS_DIR / "experiment_results.json") -> dict | None:
    """4. Cost avoided by NOT running the blanket discount (from the synthetic experiment)."""
    if not exp_results_path.exists():
        return None
    r = json.loads(exp_results_path.read_text())
    return {"opportunity": "4. Avoid unprofitable blanket discount",
            "expected_incremental_contribution_per_eligible": r["expected_incremental_per_eligible"],
            "eligible": r["config"]["n_eligible"],
            "expected_loss_avoided_per_campaign": -r["expected_incremental_per_eligible"] * r["config"]["n_eligible"],
            "evidence_type": "SIMULATED (assumption-driven)"}


MEASUREMENT_PLANS = {
    "1. Improve 12-month repeat rate": "Randomized holdout on a retention programme (e.g. post-delivery reminder / "
        "personalised recommendation); primary metric 90-day repeat rate per new customer; read at 90 and 365 days.",
    "2. Reduce canceled/unavailable orders": "Track failed-order rate weekly by seller and stage; pilot stock-sync / "
        "seller SLA with the top sellers by unavailable orders vs matched control sellers (diff-in-diff).",
    "3. Cut late first deliveries (upper bound)": "Randomize a delivery-promise change (buffered estimate or faster "
        "carrier) for first orders in high-delay states; measure on-time rate, review score and 180-day repeat.",
    "4. Avoid unprofitable blanket discount": "Run a powered experiment (see power table) with smaller/targeted "
        "discounts; primary metric contribution per eligible customer.",
}


def main() -> pd.DataFrame:
    b = baselines()
    t = size(b)
    t["measurement_plan"] = t.opportunity.map(MEASUREMENT_PLANS)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    t.to_csv(RESULTS_DIR / "opportunity_sizing.csv", index=False)
    disc = discount_avoidance()
    (RESULTS_DIR / "opportunity_baselines.json").write_text(json.dumps({"baselines": b, "discount": disc,
        "assumptions": {"contribution_margin": ExperimentConfig().contribution_margin,
                        "variable_cost_per_order": ExperimentConfig().variable_cost_per_order}}, indent=2))
    from src.db import engine
    t.to_sql("opportunity_sizing", engine(), schema="analytics", if_exists="replace", index=False)
    pd.set_option("display.width", 250)
    print(json.dumps(b, indent=1))
    print(t[["opportunity", "scenario", "affected_units", "incremental_gmv", "incremental_contribution",
             "gmv_pct_of_ltm"]].round(3).to_string())
    print(disc)
    return t


if __name__ == "__main__":
    main()
