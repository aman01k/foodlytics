"""Execute every named analysis query (Modules A-C), save results to
reports/results/*.csv, and compute the few statistics that need Python."""
from __future__ import annotations

import json

import numpy as np
from scipy import stats

from config.settings import RESULTS_DIR, SQL_DIR
from src.db import named_queries, query

MODULE_FILES = ["revenue_analysis.sql", "customer_retention.sql", "category_analysis.sql"]


def run_all() -> dict:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for f in MODULE_FILES:
        for name, sql in named_queries(SQL_DIR / f).items():
            df = query(sql)
            df.to_csv(RESULTS_DIR / f"{name}.csv", index=False)
            out[name] = df
    return out


def review_gap_test(df) -> dict:
    """Welch t-test of review score, on-time vs late (from group summaries)."""
    on, late = df[df.is_on_time].iloc[0], df[~df.is_on_time].iloc[0]
    t, p = stats.ttest_ind_from_stats(on.avg_review, on.sd_review, on.orders,
                                      late.avg_review, late.sd_review, late.orders, equal_var=False)
    diff = on.avg_review - late.avg_review
    se = np.sqrt(on.sd_review**2 / on.orders + late.sd_review**2 / late.orders)
    return {"on_time_avg": float(on.avg_review), "late_avg": float(late.avg_review),
            "diff": float(diff), "ci95": [float(diff - 1.96 * se), float(diff + 1.96 * se)],
            "t": float(t), "p_value": float(p), "late_orders": int(late.orders)}


def main() -> dict:
    res = run_all()
    extra = {"review_on_time_vs_late": review_gap_test(res["a12_late_vs_ontime_review"])}
    (RESULTS_DIR / "python_stats.json").write_text(json.dumps(extra, indent=2))
    print(f"saved {len(res)} result tables to {RESULTS_DIR}")
    return {**res, **extra}


if __name__ == "__main__":
    main()
