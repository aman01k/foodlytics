"""Module D - statistical analysis of the SYNTHETIC discount experiment.

Pre-registered analysis plan (fixed before looking at any simulated outcome):
  Primary metric : contribution profit per ELIGIBLE customer over the 60-day window
                   (all assigned customers in the denominator, converters or not).
  Secondary      : conversion rate (>=1 order in window).
  Guardrails     : AOV of converters, discount cost per eligible customer.
  Test level     : two-sided alpha = 0.05; 80% power target.
  Methods        : conversion -> two-proportion z-test + Wald CI on the difference,
                   delta-method CI on the relative lift.
                   per-customer money metrics (zero-inflated, heavy-tailed) ->
                   Welch t-test (valid by CLT at these n) + bootstrap percentile CI
                   as a distribution-free check.
"""
from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize, proportions_ztest

from config.settings import RESULTS_DIR
from src.experiment_simulator import ExperimentConfig, load_calibration, resolve, simulate

ALPHA = 0.05
Z = stats.norm.ppf(1 - ALPHA / 2)


# ----------------------------------------------------------------------------- tests
def conversion_test(df: pd.DataFrame) -> dict:
    g = df.groupby("group")["converted"].agg(["sum", "count"])
    x_t, n_t = int(g.loc["treatment", "sum"]), int(g.loc["treatment", "count"])
    x_c, n_c = int(g.loc["control", "sum"]), int(g.loc["control", "count"])
    p_t, p_c = x_t / n_t, x_c / n_c
    z, p = proportions_ztest([x_t, x_c], [n_t, n_c], alternative="two-sided")
    se = np.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c)
    diff = p_t - p_c
    rel = p_t / p_c - 1 if p_c > 0 else np.nan
    # delta method on log(p_t/p_c)
    if x_t > 0 and x_c > 0:
        se_log = np.sqrt((1 - p_t) / x_t + (1 - p_c) / x_c)
        rel_ci = [float(np.exp(np.log(p_t / p_c) - Z * se_log) - 1),
                  float(np.exp(np.log(p_t / p_c) + Z * se_log) - 1)]
    else:
        rel_ci = [np.nan, np.nan]
    return {"control_rate": p_c, "treatment_rate": p_t, "control_conversions": x_c,
            "treatment_conversions": x_t, "n_control": n_c, "n_treatment": n_t,
            "abs_lift": diff, "abs_lift_ci": [diff - Z * se, diff + Z * se],
            "rel_lift": rel, "rel_lift_ci": rel_ci, "z": float(z), "p_value": float(p)}


def mean_diff_test(t: np.ndarray, c: np.ndarray, n_boot: int = 1000, seed: int = 0) -> dict:
    """Welch t-test + bootstrap percentile CI for mean(t) - mean(c)."""
    diff = t.mean() - c.mean()
    if len(t) < 2 or len(c) < 2:
        return {"control_mean": float(c.mean()) if len(c) else np.nan,
                "treatment_mean": float(t.mean()) if len(t) else np.nan,
                "diff": float(diff), "ci": [np.nan, np.nan], "p_value": np.nan,
                "boot_ci": [np.nan, np.nan]}
    vt, vc = t.var(ddof=1) / len(t), c.var(ddof=1) / len(c)
    se = np.sqrt(vt + vc)
    tt = stats.ttest_ind(t, c, equal_var=False)
    if n_boot == 0:  # analytic CI only (used by Monte Carlo for speed)
        return {"control_mean": float(c.mean()), "treatment_mean": float(t.mean()),
                "diff": float(diff), "ci": [float(diff - Z * se), float(diff + Z * se)],
                "p_value": float(tt.pvalue), "boot_ci": [np.nan, np.nan]}
    rng = np.random.default_rng(seed)
    # bootstrap the mean via resampled index sums (memory-light, vectorized in chunks)
    boots = np.empty(n_boot)
    for i in range(0, n_boot, 100):
        k = min(100, n_boot - i)
        bt = t[rng.integers(0, len(t), (k, len(t)))].mean(axis=1)
        bc = c[rng.integers(0, len(c), (k, len(c)))].mean(axis=1)
        boots[i:i + k] = bt - bc
    return {"control_mean": float(c.mean()), "treatment_mean": float(t.mean()),
            "diff": float(diff), "ci": [float(diff - Z * se), float(diff + Z * se)],
            "p_value": float(tt.pvalue),
            "boot_ci": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]}


def summarize_groups(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("group")
    out = pd.DataFrame({
        "eligible_customers": g.size(),
        "conversions": g.converted.sum(),
        "conversion_rate": g.converted.mean(),
        "orders": g.n_orders.sum(),
        "gmv": g.gmv.sum(),
        "aov_gmv": g.gmv.sum() / g.n_orders.sum().replace(0, np.nan),
        "gmv_per_eligible": g.gmv.mean(),
        "net_revenue_per_eligible": g.net_revenue.mean(),
        "discount_cost_per_eligible": g.discount_cost.mean(),
        "contribution_per_eligible": g.contribution.mean(),
        "total_contribution": g.contribution.sum(),
    })
    return out.T[["control", "treatment"]]


# --------------------------------------------------------------------- decision rule
def decide(conv: dict, profit: dict, alpha: float = ALPHA) -> dict:
    """Map results to the three business outcomes. Computed, never hardcoded."""
    conv_up = conv["p_value"] < alpha and conv["abs_lift"] > 0
    lo, hi = profit["ci"]
    if lo > 0:
        code, label = 1, "LAUNCH: conversion and contribution profit both improve"
        action = ("Roll out to the eligible segment with a holdout group to keep "
                  "measuring incrementality.")
    elif conv_up and hi < 0:
        code, label = 2, "DO NOT LAUNCH AS DESIGNED: conversion up, contribution profit down"
        action = ("The discount buys orders at a loss. Test a smaller discount, a "
                  "minimum-basket threshold, or target only customers with low baseline "
                  "propensity (where fewer discounts go to customers who would buy anyway).")
    elif conv_up:
        code, label = 2, "DO NOT LAUNCH YET: conversion up, profit impact not resolved"
        action = ("Conversion improved but the profit CI spans zero. Do not scale; "
                  "extend the test or re-run with the sample size from the power analysis.")
    else:
        code, label = 3, "NO RELIABLE IMPROVEMENT: do not launch"
        action = ("No statistically reliable conversion lift at this sample size. "
                  "Do not spend on the campaign; if the idea is still attractive, re-test "
                  "with a design powered for the minimum lift that would be profitable.")
        if hi < 0:
            label += " (and contribution profit is significantly lower)"
    return {"outcome_code": code, "decision": label, "recommended_action": action,
            "conversion_significant": bool(conv_up),
            "profit_ci_lower": lo, "profit_ci_upper": hi}


# ---------------------------------------------------------------- break-even & sens.
def unit_economics(cfg: ExperimentConfig) -> dict:
    a = float(np.mean(cfg.order_values))
    k = 1 + cfg.extra_orders_rate
    return {"avg_order_value": a, "orders_per_converter": k}


def expected_incremental(cfg: ExperimentConfig, rel_lift: float | None = None,
                         discount: float | None = None, margin: float | None = None) -> float:
    """Expected incremental contribution per eligible customer (closed form)."""
    u = unit_economics(cfg)
    a, k = u["avg_order_value"], u["orders_per_converter"]
    d = cfg.discount_pct if discount is None else discount
    m = cfg.contribution_margin if margin is None else margin
    L = cfg.relative_lift if rel_lift is None else rel_lift
    p0, c = cfg.baseline_conversion, cfg.variable_cost_per_order
    p1 = min(p0 * (1 + L), 1.0)
    at = a * (1 + cfg.aov_uplift_treated)
    return p1 * k * ((m - d) * at - c) - p0 * k * (m * a - c)


def break_even(cfg: ExperimentConfig, discount: float | None = None, margin: float | None = None) -> dict:
    u = unit_economics(cfg)
    a = u["avg_order_value"]
    d = cfg.discount_pct if discount is None else discount
    m = cfg.contribution_margin if margin is None else margin
    c = cfg.variable_cost_per_order
    at = a * (1 + cfg.aov_uplift_treated)
    ctrl_unit, trt_unit = m * a - c, (m - d) * at - c
    if trt_unit <= 0:
        return {"break_even_rel_lift": np.inf, "break_even_conversion": np.inf,
                "note": "discount exceeds unit contribution: no lift can break even"}
    ratio = ctrl_unit / trt_unit
    return {"break_even_rel_lift": ratio - 1,
            "break_even_conversion": cfg.baseline_conversion * ratio,
            "break_even_abs_lift": cfg.baseline_conversion * (ratio - 1),
            "control_unit_contribution": ctrl_unit, "treated_unit_contribution": trt_unit}


def break_even_discount(cfg: ExperimentConfig, rel_lift: float) -> float:
    """Largest discount that still breaks even if the lift is `rel_lift`."""
    a = unit_economics(cfg)["avg_order_value"]
    m, c = cfg.contribution_margin, cfg.variable_cost_per_order
    at = a * (1 + cfg.aov_uplift_treated)
    return m * a / at - ((m * a - c) / (1 + rel_lift) + c) / at


def sensitivity_tables(cfg: ExperimentConfig) -> dict[str, pd.DataFrame]:
    discounts = [0.03, 0.05, 0.10, 0.15, 0.20]
    lifts = [0.0, 0.10, 0.25, 0.50, 1.00, 2.00, 3.00]
    margins = [0.10, 0.15, 0.20, 0.25, 0.30]
    g1 = pd.DataFrame([{"discount_pct": d, "relative_lift": L,
                        "incr_contribution_per_1000_eligible": 1000 * expected_incremental(cfg, L, d)}
                       for d in discounts for L in lifts])
    g2 = pd.DataFrame([{"contribution_margin": m, "discount_pct": d,
                        "break_even_rel_lift": break_even(cfg, d, m)["break_even_rel_lift"]}
                       for m in margins for d in discounts])
    g3 = pd.DataFrame([{"relative_lift": L, "break_even_discount": break_even_discount(cfg, L)}
                       for L in [0.05, 0.10, 0.15, 0.25, 0.50, 1.00]])
    return {"sens_discount_x_lift": g1, "sens_margin_x_discount": g2, "sens_breakeven_discount": g3}


# ------------------------------------------------------------------------- power
def power_analysis(cfg: ExperimentConfig, n_per_arm: int, profit_sd: float) -> dict:
    p0, L = cfg.baseline_conversion, cfg.relative_lift
    p1 = p0 * (1 + L)
    solver = NormalIndPower()
    h = proportion_effectsize(p1, p0)
    need = solver.solve_power(effect_size=h, alpha=ALPHA, power=0.8, ratio=1.0)
    achieved = solver.power(effect_size=h, nobs1=n_per_arm, alpha=ALPHA, ratio=1.0)
    mde_h = solver.solve_power(nobs1=n_per_arm, alpha=ALPHA, power=0.8, ratio=1.0)
    # invert Cohen's h for p1: h = 2 asin(sqrt p1) - 2 asin(sqrt p0)
    mde_p1 = np.sin(np.arcsin(np.sqrt(p0)) + mde_h / 2) ** 2
    be = break_even(cfg)
    rows = []
    for rel in [0.10, 0.15, 0.25, 0.50, 1.00, be["break_even_rel_lift"]]:
        if not np.isfinite(rel):
            continue
        hh = proportion_effectsize(min(p0 * (1 + rel), 1), p0)
        rows.append({"relative_lift": rel,
                     "n_per_arm_for_80pct_power": int(np.ceil(solver.solve_power(hh, alpha=ALPHA, power=0.8)))})
    return {"assumed_rel_lift": L, "n_per_arm_actual": n_per_arm,
            "n_per_arm_needed_for_assumed_lift": int(np.ceil(need)),
            "power_at_actual_n": float(achieved),
            "mde_rel_lift_at_actual_n": float(mde_p1 / p0 - 1),
            "profit_mde_per_eligible": float(2.8 * profit_sd * np.sqrt(2 / n_per_arm)),
            "sample_size_table": rows}


def sample_size(p0: float, rel_lift: float, alpha: float = ALPHA, power: float = 0.8) -> int:
    h = proportion_effectsize(min(p0 * (1 + rel_lift), 1), p0)
    return int(np.ceil(NormalIndPower().solve_power(h, alpha=alpha, power=power)))


# ------------------------------------------------------------------------ pipeline
def analyze(cfg: ExperimentConfig, cal: dict | None = None, n_boot: int = 1000) -> dict:
    cal = cal or load_calibration()
    rc = resolve(cfg, cal)
    df = simulate(rc, cal)
    t, c = df[df.group == "treatment"], df[df.group == "control"]
    conv = conversion_test(df)
    profit = mean_diff_test(t.contribution.to_numpy(), c.contribution.to_numpy(), n_boot, rc.seed)
    revenue = mean_diff_test(t.net_revenue.to_numpy(), c.net_revenue.to_numpy(), n_boot, rc.seed + 1)
    aov = mean_diff_test((t.gmv / t.n_orders)[t.converted].to_numpy(),
                         (c.gmv / c.n_orders)[c.converted].to_numpy(), n_boot, rc.seed + 2)
    return {
        "config": rc.public(), "calibration_source": cal["source"],
        "is_synthetic": True,
        "groups": summarize_groups(df),
        "conversion": conv, "contribution_per_eligible": profit,
        "net_revenue_per_eligible": revenue, "aov_converters": aov,
        "incremental_contribution_if_rolled_out": profit["diff"] * rc.n_eligible,
        "decision": decide(conv, profit),
        "break_even": break_even(rc), "unit_economics": unit_economics(rc),
        "expected_incremental_per_eligible": expected_incremental(rc),
        "power": power_analysis(rc, int(len(df) * rc.treatment_share),
                                float(df.contribution.std())),
        "sensitivity": sensitivity_tables(rc),
        "data": df,
    }


def monte_carlo(cfg: ExperimentConfig, runs: int = 200, cal: dict | None = None) -> pd.DataFrame:
    """Re-run the whole experiment under different seeds: how often would each
    decision be reached if the assumptions were true? (empirical power)"""
    cal = cal or load_calibration()
    rows = []
    for s in range(runs):
        r = analyze(replace(cfg, seed=10_000 + s), cal, n_boot=0)
        rows.append({"seed": 10_000 + s, "outcome_code": r["decision"]["outcome_code"],
                     "conv_p": r["conversion"]["p_value"], "rel_lift": r["conversion"]["rel_lift"],
                     "profit_diff": r["contribution_per_eligible"]["diff"]})
    return pd.DataFrame(rows)


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items() if k not in ("data", "groups", "sensitivity")}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    return o


def save(res: dict, mc: pd.DataFrame | None = None, to_db: bool = True) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "experiment_results.json").write_text(json.dumps(_jsonable(res), indent=2))
    res["groups"].to_csv(RESULTS_DIR / "experiment_groups.csv")
    for k, v in res["sensitivity"].items():
        v.to_csv(RESULTS_DIR / f"experiment_{k}.csv", index=False)
    if mc is not None:
        mc.to_csv(RESULTS_DIR / "experiment_monte_carlo.csv", index=False)
    if to_db:
        from src.db import engine
        eng = engine()
        res["data"].to_sql("exp_customers", eng, schema="analytics", if_exists="replace", index=False)
        g = res["groups"].reset_index(names="metric")
        g.to_sql("exp_group_summary", eng, schema="analytics", if_exists="replace", index=False)
        for k, v in res["sensitivity"].items():
            v.to_sql(f"exp_{k}", eng, schema="analytics", if_exists="replace", index=False)
        if mc is not None:
            mc.to_sql("exp_monte_carlo", eng, schema="analytics", if_exists="replace", index=False)


def main(runs: int = 200) -> dict:
    cfg = ExperimentConfig()
    res = analyze(cfg)
    mc = monte_carlo(cfg, runs)
    res["monte_carlo_outcome_shares"] = mc.outcome_code.value_counts(normalize=True).sort_index().to_dict()
    save(res, mc)
    print(res["groups"].round(4).to_string())
    for k in ["conversion", "contribution_per_eligible", "decision", "break_even", "power",
              "monte_carlo_outcome_shares"]:
        print(k, json.dumps(_jsonable(res[k]), indent=1))
    return res


if __name__ == "__main__":
    main()
