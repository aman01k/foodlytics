"""Cohort retention: recompute independently in pandas and compare to SQL."""
import pandas as pd
import pytest

from tests.conftest import needs_db


@pytest.fixture(scope="module")
def frames():
    from src.db import query
    orders = query("""SELECT customer_unique_id, purchase_month FROM analytics.fct_orders
                      WHERE is_valid AND purchase_ts < '2018-09-01'""")
    sql = query("SELECT * FROM analytics.v_cohort_retention")
    return orders, sql


@needs_db
@pytest.mark.parametrize("cohort,k", [("2017-03-01", 1), ("2017-05-01", 3), ("2017-11-01", 6), ("2018-02-01", 2)])
def test_retention_matches_pandas(frames, cohort, k):
    orders, sql = frames
    orders = orders.assign(purchase_month=pd.to_datetime(orders.purchase_month))
    first = orders.groupby("customer_unique_id").purchase_month.min().rename("cohort")
    o = orders.join(first, on="customer_unique_id")
    c = pd.Timestamp(cohort)
    members = first[first == c].index
    target = c + pd.DateOffset(months=k)
    active = o[(o.cohort == c) & (o.purchase_month == target)].customer_unique_id.nunique()
    expected = active / len(members)
    row = sql[(pd.to_datetime(sql.cohort_month) == c) & (sql.months_since_first == k)].iloc[0]
    assert row.cohort_size == len(members)
    assert float(row.retention_rate) == pytest.approx(expected)


@needs_db
def test_unobservable_cells_are_null_not_zero(frames):
    _, sql = frames
    late = sql[(pd.to_datetime(sql.cohort_month) == pd.Timestamp("2018-08-01")) & (sql.months_since_first >= 1)]
    assert late.retention_rate.isna().all()
    assert not late.is_observable.any()


@needs_db
def test_repeat_rate_definition():
    from src.db import query
    r = query("""SELECT AVG((n_purchase_days >= 2)::int) a, (SELECT repeat_rate FROM analytics.v_customer_overview) b
                 FROM analytics.dim_customers""").iloc[0]
    assert float(r.a) == pytest.approx(float(r.b))
