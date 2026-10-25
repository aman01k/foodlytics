"""KPI correctness: recompute headline KPIs independently in pandas from the
cleaned files and compare with the SQL views and the dashboard queries."""
import numpy as np
import pandas as pd
import pytest

from config.settings import PROCESSED_DIR
from tests.conftest import needs_db

START, END = pd.Timestamp("2017-01-01"), pd.Timestamp("2018-09-01")


@pytest.fixture(scope="module")
def pandas_kpis():
    o = pd.read_csv(PROCESSED_DIR / "orders.csv", parse_dates=["order_purchase_timestamp"])
    i = pd.read_csv(PROCESSED_DIR / "order_items.csv")
    gmv = i.groupby("order_id").price.sum()
    o = o[(o.order_purchase_timestamp >= START) & (o.order_purchase_timestamp < END)].copy()
    o["gmv"] = o.order_id.map(gmv)
    valid = o[~o.order_status.isin(["canceled", "unavailable"]) & o.gmv.notna()]
    return {"total_orders": len(o), "valid_orders": len(valid), "gmv": valid.gmv.sum(),
            "aov_gmv": valid.gmv.mean(), "cancellation_rate": (o.order_status == "canceled").mean(),
            "failed_order_rate": o.order_status.isin(["canceled", "unavailable"]).mean()}


@needs_db
def test_sql_kpis_match_pandas(pandas_kpis):
    from src.db import query
    s = query("SELECT * FROM analytics.v_kpi_summary").iloc[0]
    assert s.total_orders == pandas_kpis["total_orders"]
    assert s.valid_orders == pandas_kpis["valid_orders"]
    assert float(s.gmv) == pytest.approx(pandas_kpis["gmv"], abs=0.05)
    assert float(s.aov_gmv) == pytest.approx(pandas_kpis["aov_gmv"], abs=0.01)
    assert float(s.cancellation_rate) == pytest.approx(pandas_kpis["cancellation_rate"], abs=1e-5)
    assert float(s.failed_order_rate) == pytest.approx(pandas_kpis["failed_order_rate"], abs=1e-5)


@needs_db
def test_dashboard_kpis_match_sql_views():
    from dashboard import queries as q
    from src.db import query
    m = q.months()
    k = q.kpis(m[0], m[-1], "All")
    s = query("SELECT * FROM analytics.v_kpi_summary").iloc[0]
    assert k["valid_orders"] == s.valid_orders
    assert float(k["gmv"]) == pytest.approx(float(s.gmv), abs=0.05)
    assert float(k["aov"]) == pytest.approx(float(s.aov_gmv), abs=0.01)
    assert float(k["on_time_rate"]) == pytest.approx(float(s.on_time_rate), abs=1e-4)
    assert k["order_growth"] is None  # no comparable prior period for the full window


@needs_db
def test_monthly_sums_to_total():
    from src.db import query
    m = query("SELECT SUM(valid_orders) AS o, SUM(gmv) AS g FROM analytics.v_kpi_monthly").iloc[0]
    s = query("SELECT valid_orders, gmv FROM analytics.v_kpi_summary").iloc[0]
    assert m.o == s.valid_orders and float(m.g) == pytest.approx(float(s.gmv), abs=0.05)


@needs_db
def test_naive_join_would_double_count():
    """Demonstrates why items and payments are aggregated before joining."""
    from src.db import query
    naive = query("""SELECT SUM(i.price) AS g FROM clean.order_items i
                     JOIN clean.order_payments p USING (order_id)""").g.iloc[0]
    correct = query("SELECT SUM(gmv) AS g FROM analytics.fct_orders").g.iloc[0]
    assert float(naive) > float(correct) * 1.01
    assert float(correct) == pytest.approx(float(query("SELECT SUM(price) g FROM clean.order_items").g.iloc[0]))


@needs_db
def test_category_gmv_reconciles_to_total():
    from src.db import query
    c = query("SELECT SUM(gmv) g FROM analytics.v_category_performance").g.iloc[0]
    s = query("SELECT gmv FROM analytics.v_kpi_summary").gmv.iloc[0]
    assert float(c) == pytest.approx(float(s), abs=0.05)
