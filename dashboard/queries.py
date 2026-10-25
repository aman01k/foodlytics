"""All dashboard data access. Every number on the dashboard comes from these
parameterized SQL queries against the analytics schema - no hardcoded KPIs.
Kept separate from app.py so tests can check them against the SQL views."""
from __future__ import annotations

import pandas as pd

from src.db import query

# Tooltip text = the documented metric definitions (reports/metric_definitions.md)
DEFINITIONS = {
    "orders": "Valid orders: status not canceled/unavailable and at least one line item.",
    "gmv": "GMV = sum of item prices (excl. freight) of valid orders, in BRL. Not company revenue.",
    "aov": "Average order value = GMV / valid orders (excl. freight).",
    "cancel": "Cancellation rate = orders with status 'canceled' / all orders placed.",
    "failed": "Failed-order rate = canceled + unavailable orders / all orders placed.",
    "on_time": "On-time = delivered on or before the estimated delivery date shown to the customer.",
    "growth": "Order growth vs the immediately preceding period of equal length.",
    "repeat": "Repeat customer = valid purchases on 2+ distinct days (customer_unique_id).",
    "retention": "Share of a first-purchase-month cohort with a valid order k months later. "
                 "Blank cells are not yet observable.",
}


def _filters(state: str | None) -> str:
    return "" if not state or state == "All" else "AND customer_state = :state"


def months() -> list:
    return query("SELECT DISTINCT purchase_month FROM analytics.fct_orders WHERE in_window ORDER BY 1"
                 ).purchase_month.tolist()


def states() -> list[str]:
    return ["All"] + query("SELECT DISTINCT customer_state FROM analytics.fct_orders ORDER BY 1"
                           ).customer_state.tolist()


_KPI_SQL = """
    SELECT COUNT(*) FILTER (WHERE is_valid)               AS valid_orders,
           COUNT(*)                                       AS total_orders,
           SUM(gmv) FILTER (WHERE is_valid)               AS gmv,
           AVG(gmv) FILTER (WHERE is_valid)               AS aov,
           AVG(is_canceled::int)                          AS cancellation_rate,
           AVG((is_canceled OR is_unavailable)::int)      AS failed_order_rate,
           AVG(is_on_time::int)                           AS on_time_rate,
           AVG(review_score)                              AS avg_review,
           COUNT(DISTINCT customer_unique_id) FILTER (WHERE is_valid) AS customers
    FROM analytics.fct_orders
    WHERE in_window AND purchase_month BETWEEN :start AND :end {flt}"""


def kpis(start, end, state: str | None = None) -> dict:
    """KPIs for [start, end] plus the same KPIs for the immediately preceding
    period of equal length (`prev`, None when the window has no such period)."""
    cur = query(_KPI_SQL.format(flt=_filters(state)), start=start, end=end, state=state).iloc[0].to_dict()
    ms = months()
    sel = [m for m in ms if start <= m <= end]
    before = [m for m in ms if m < start]
    prev = None
    if len(before) >= len(sel):
        p_start, p_end = before[-len(sel)], before[-1]
        prev = query(_KPI_SQL.format(flt=_filters(state)), start=p_start, end=p_end, state=state).iloc[0].to_dict()
        prev["period"] = (p_start, p_end)
    cur["prev"] = prev
    cur["order_growth"] = cur["valid_orders"] / prev["valid_orders"] - 1 if prev and prev["valid_orders"] else None
    cur["gmv_growth"] = cur["gmv"] / prev["gmv"] - 1 if prev and prev["gmv"] else None
    return cur


def insights() -> dict:
    """Headline facts for the takeaway panel (whole analysis window)."""
    yoy = query("SELECT * FROM analytics.v_yoy_growth").iloc[0].to_dict()
    dec = query("""SELECT SUM(ABS(volume_effect)) / SUM(ABS(volume_effect) + ABS(value_effect)
                          + ABS(interaction_effect)) AS volume_share FROM analytics.v_gmv_decomposition""").iloc[0]
    rev = query("""SELECT AVG(review_score) FILTER (WHERE is_on_time) AS on_time,
                          AVG(review_score) FILTER (WHERE NOT is_on_time) AS late
                   FROM analytics.fct_orders WHERE in_window AND is_delivered""").iloc[0]
    rep = query("SELECT repeat_rate FROM analytics.v_customer_overview").iloc[0]
    return {**yoy, "volume_share": float(dec.volume_share), "review_on_time": float(rev.on_time),
            "review_late": float(rev.late), "repeat_rate": float(rep.repeat_rate)}


def monthly(start, end, state: str | None = None) -> pd.DataFrame:
    return query(f"""
        SELECT purchase_month AS month,
               COUNT(*) FILTER (WHERE is_valid) AS valid_orders,
               SUM(gmv) FILTER (WHERE is_valid) AS gmv,
               AVG(gmv) FILTER (WHERE is_valid) AS aov,
               AVG(is_canceled::int) AS cancellation_rate,
               AVG((is_canceled OR is_unavailable)::int) AS failed_order_rate,
               AVG(is_on_time::int) AS on_time_rate,
               AVG(review_score) AS avg_review
        FROM analytics.fct_orders
        WHERE in_window AND purchase_month BETWEEN :start AND :end {_filters(state)}
        GROUP BY 1 ORDER BY 1""", start=start, end=end, state=state)


def gmv_decomposition(start, end) -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_gmv_decomposition WHERE month BETWEEN :start AND :end",
                 start=start, end=end)


def delivery_vs_review() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_delivery_vs_review")


# ---------------------------------------------------------------- customers
def segments() -> list[str]:
    return ["All"] + query("SELECT DISTINCT segment FROM analytics.dim_customers ORDER BY 1").segment.tolist()


def customer_overview(segment: str = "All") -> dict:
    where = "" if segment == "All" else "WHERE segment = :segment"
    return query(f"""
        SELECT COUNT(*) AS customers, AVG(is_repeat::int) AS repeat_rate,
               AVG(total_gmv) AS avg_gmv, AVG(recency_days) AS avg_recency,
               SUM(total_gmv) AS gmv
        FROM analytics.dim_customers {where}""", segment=segment).iloc[0].to_dict()


def new_vs_returning(start, end) -> pd.DataFrame:
    return query("""SELECT month, new_customers, returning_customers FROM analytics.v_kpi_monthly
                    WHERE month BETWEEN :start AND :end ORDER BY month""", start=start, end=end)


def cohort_matrix(max_k: int = 12) -> pd.DataFrame:
    df = query("""SELECT cohort_month, cohort_size, months_since_first, retention_rate
                  FROM analytics.v_cohort_retention WHERE months_since_first <= :k""", k=max_k)
    return df


def segment_table() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_customer_segments")


def frequency() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_order_frequency")


def purchase_gaps() -> pd.DataFrame:
    return query("SELECT gap_days FROM analytics.v_purchase_gaps")


def repeat_within_days() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_repeat_within_days")


def segment_thresholds() -> dict:
    return query("SELECT * FROM analytics.v_segment_thresholds").iloc[0].to_dict()


# ---------------------------------------------------------------- categories
def categories() -> list[str]:
    return query("SELECT category FROM analytics.v_category_performance ORDER BY gmv DESC").category.tolist()


def category_performance(start, end, state: str | None = None) -> pd.DataFrame:
    return query(f"""
        WITH it AS (SELECT * FROM analytics.fct_order_items
                    WHERE in_window AND is_valid AND purchase_month BETWEEN :start AND :end {_filters(state)}),
        oc AS (SELECT DISTINCT order_id, category, review_score, is_on_time, delivery_days FROM it),
        q AS (SELECT category, AVG(review_score) AS avg_review, AVG((review_score <= 2)::int) AS share_1_2_star,
                     AVG(is_on_time::int) AS on_time_rate, AVG(delivery_days) AS avg_delivery_days
              FROM oc GROUP BY 1)
        SELECT it.category, SUM(price) AS gmv, COUNT(*) AS items, COUNT(DISTINCT order_id) AS orders,
               AVG(price) AS avg_item_price, COUNT(DISTINCT seller_id) AS sellers,
               SUM(price) / SUM(SUM(price)) OVER () AS gmv_share,
               RANK() OVER (ORDER BY SUM(price) DESC) AS gmv_rank,
               MAX(q.avg_review) AS avg_review, MAX(q.share_1_2_star) AS share_1_2_star,
               MAX(q.on_time_rate) AS on_time_rate, MAX(q.avg_delivery_days) AS avg_delivery_days
        FROM it JOIN q USING (category) GROUP BY it.category ORDER BY gmv DESC""",
                 start=start, end=end, state=state)


def category_monthly(cats: list[str], start, end) -> pd.DataFrame:
    if not cats:
        return pd.DataFrame(columns=["month", "category", "gmv"])
    return query("""SELECT * FROM analytics.v_category_monthly
                    WHERE category = ANY(:cats) AND month BETWEEN :start AND :end ORDER BY month""",
                 cats=list(cats), start=start, end=end)


def seller_concentration() -> dict:
    return query("SELECT * FROM analytics.v_seller_concentration").iloc[0].to_dict()


# ---------------------------------------------------------------- experiment (synthetic)
def exp_group_summary() -> pd.DataFrame:
    return query("SELECT * FROM analytics.exp_group_summary")


def opportunity_table() -> pd.DataFrame:
    return query("SELECT * FROM analytics.opportunity_sizing")
