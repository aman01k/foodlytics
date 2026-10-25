"""Module D - SYNTHETIC discount A/B test simulator.

Nothing produced by this module is historical Olist data. The Olist dataset has
no randomized promotion, so we simulate one. Historical data is used only to
CALIBRATE the control group (baseline conversion and order values); the
treatment effect is an explicit, configurable ASSUMPTION.

Hypothetical campaign
    Eligible: one-time buyers whose only purchase day was 31-365 days ago.
    Control:  no promotion.  Treatment: 10% off their next order.
    Window:   60 days after assignment.

Calibration (historical back-test, not a simulation)
    At a past snapshot S = 2018-07-01 we apply the same eligibility rule and
    measure the share who actually purchased within [S, S+60d). That observed
    rate is the control conversion. Order values are resampled from real
    repeat-purchase orders.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from config.settings import RANDOM_SEED, RESULTS_DIR

CALIBRATION_FILE = RESULTS_DIR / "experiment_calibration.json"

CALIBRATION_SQL = {
    # Observed 60-day purchase rate of eligible one-time buyers at a past snapshot.
    "baseline": """
        WITH days AS (
            SELECT DISTINCT customer_unique_id, purchase_ts::date AS d
            FROM analytics.fct_orders WHERE is_valid
        ), hist AS (
            SELECT customer_unique_id, COUNT(*) AS n_days, MAX(d) AS last_d
            FROM days WHERE d < CAST(:snap AS date) GROUP BY 1
        ), elig AS (
            SELECT customer_unique_id FROM hist
            WHERE n_days = 1 AND CAST(:snap AS date) - last_d BETWEEN 31 AND 365
        ), conv AS (
            SELECT DISTINCT customer_unique_id FROM days
            WHERE d >= CAST(:snap AS date) AND d < CAST(:snap AS date) + CAST(:window AS int)
        )
        SELECT COUNT(*) AS eligible, COUNT(c.customer_unique_id) AS converted
        FROM elig e LEFT JOIN conv c USING (customer_unique_id)""",
    # Size of the eligible population at the end of the data (the 'next' campaign).
    "population": """
        SELECT COUNT(*) AS n FROM analytics.dim_customers
        WHERE n_purchase_days = 1 AND recency_days BETWEEN 31 AND 365""",
    # Real repeat-purchase order values (orders on a customer's 2nd+ purchase day).
    "order_values": """
        SELECT f.gmv FROM analytics.fct_orders f
        JOIN analytics.dim_customers c USING (customer_unique_id)
        WHERE f.is_valid AND f.purchase_ts::date > c.first_purchase_ts::date
        ORDER BY f.order_id  -- deterministic order => seed-reproducible resampling""",
    # Extra purchase days within 60d among customers who repeat (multi-order converters).
    "extra_orders": """
        WITH days AS (SELECT DISTINCT customer_unique_id, purchase_ts::date d
                      FROM analytics.fct_orders WHERE is_valid),
        fr AS (SELECT customer_unique_id, MIN(d) AS first_repeat FROM days d
               JOIN analytics.dim_customers c USING (customer_unique_id)
               WHERE d.d > c.first_purchase_ts::date GROUP BY 1)
        SELECT AVG(n - 1) AS extra_orders_rate FROM (
            SELECT fr.customer_unique_id, COUNT(*) AS n FROM fr JOIN days USING (customer_unique_id)
            WHERE days.d >= fr.first_repeat AND days.d < fr.first_repeat + 60 GROUP BY 1) x""",
}


@dataclass
class ExperimentConfig:
    """Every number that drives the simulation. Defaults are documented in
    reports/experiment_methodology.md. Values marked ASSUMPTION are not
    observable in Olist and must be varied in sensitivity analysis."""
    n_eligible: int | None = None          # None -> real eligible population size
    treatment_share: float = 0.5
    discount_pct: float = 0.10
    baseline_conversion: float | None = None  # None -> calibrated (historical back-test)
    price_elasticity: float = 1.5          # ASSUMPTION: relative lift = elasticity * discount
    aov_uplift_treated: float = 0.0        # ASSUMPTION: basket-size change for treated orders
    contribution_margin: float = 0.15      # ASSUMPTION: platform contribution per R$ GMV pre-promo
    variable_cost_per_order: float = 1.50  # ASSUMPTION: R$ per order (payment/support)
    window_days: int = 60
    seed: int = RANDOM_SEED
    extra_orders_rate: float | None = None  # None -> calibrated
    order_values: np.ndarray | None = field(default=None, repr=False)

    @property
    def relative_lift(self) -> float:
        return self.price_elasticity * self.discount_pct

    def public(self) -> dict:
        d = asdict(self)
        d.pop("order_values")
        d["relative_lift_assumed"] = self.relative_lift
        return d


def calibrate(snapshot: str = "2018-07-01", window_days: int = 60, save: bool = True) -> dict:
    """Pull calibration inputs from PostgreSQL and cache them as JSON so the
    simulator and tests can run without a database."""
    from src.db import query
    b = query(CALIBRATION_SQL["baseline"], snap=snapshot, window=window_days).iloc[0]
    cal = {
        "snapshot": snapshot, "window_days": window_days,
        "backtest_eligible": int(b.eligible), "backtest_converted": int(b.converted),
        "baseline_conversion": float(b.converted / b.eligible),
        "eligible_population": int(query(CALIBRATION_SQL["population"]).n.iloc[0]),
        "extra_orders_rate": float(query(CALIBRATION_SQL["extra_orders"]).extra_orders_rate.iloc[0]),
        "order_values": query(CALIBRATION_SQL["order_values"]).gmv.round(2).tolist(),
        "source": "Historical Olist back-test (observed). Used only to calibrate the control arm.",
    }
    if save:
        CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        CALIBRATION_FILE.write_text(json.dumps(cal))
    return cal


def load_calibration() -> dict:
    if not CALIBRATION_FILE.exists():
        return calibrate()
    return json.loads(CALIBRATION_FILE.read_text())


def resolve(cfg: ExperimentConfig, cal: dict | None = None) -> ExperimentConfig:
    """Fill calibrated defaults (returns a new config)."""
    cal = cal or load_calibration()
    c = ExperimentConfig(**{**asdict(cfg)})
    c.n_eligible = c.n_eligible or cal["eligible_population"]
    c.baseline_conversion = (cal["baseline_conversion"] if c.baseline_conversion is None
                             else c.baseline_conversion)
    c.extra_orders_rate = cal["extra_orders_rate"] if c.extra_orders_rate is None else c.extra_orders_rate
    c.order_values = (np.asarray(cal["order_values"], dtype=float)
                      if cfg.order_values is None else cfg.order_values)
    return c


def simulate(cfg: ExperimentConfig, cal: dict | None = None) -> pd.DataFrame:
    """One row per synthetic eligible customer with assignment and outcomes."""
    c = resolve(cfg, cal)
    rng = np.random.default_rng(c.seed)
    n = c.n_eligible
    # Complete randomization with an exact split (no chance imbalance in arm sizes).
    n_t = int(round(n * c.treatment_share))
    treated = np.zeros(n, dtype=bool)
    treated[rng.permutation(n)[:n_t]] = True

    p = np.where(treated, min(c.baseline_conversion * (1 + c.relative_lift), 1.0),
                 c.baseline_conversion)
    converted = rng.random(n) < p
    n_orders = np.where(converted, 1 + rng.poisson(c.extra_orders_rate, n), 0)

    # Gross (list-price) GMV: sum of n_orders resampled real order values.
    max_k = int(n_orders.max()) if n else 0
    draws = rng.choice(c.order_values, size=(n, max(max_k, 1)), replace=True)
    mask = np.arange(max(max_k, 1))[None, :] < n_orders[:, None]
    gmv = (draws * mask).sum(axis=1) * np.where(treated, 1 + c.aov_uplift_treated, 1.0)

    discount_cost = np.where(treated, c.discount_pct * gmv, 0.0)
    contribution = c.contribution_margin * gmv - c.variable_cost_per_order * n_orders - discount_cost
    return pd.DataFrame({
        "customer_id": [f"SIM-{i:06d}" for i in range(n)],
        "group": np.where(treated, "treatment", "control"),
        "converted": converted,
        "n_orders": n_orders,
        "gmv": gmv.round(2),
        "net_revenue": (gmv - discount_cost).round(2),   # what customers paid
        "discount_cost": discount_cost.round(4),
        "contribution": contribution.round(4),
        "is_synthetic": True,
    })


if __name__ == "__main__":
    cal = calibrate()
    print({k: v for k, v in cal.items() if k != "order_values"}, "order values:", len(cal["order_values"]))
    df = simulate(ExperimentConfig())
    print(df.groupby("group")[["converted", "gmv", "contribution"]].mean())
