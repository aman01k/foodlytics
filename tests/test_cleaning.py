"""Cleaning rules, checked on the processed files (no DB needed)."""
import json

import pandas as pd
import pytest

from config.settings import PROCESSED_DIR

pytestmark = pytest.mark.skipif(not (PROCESSED_DIR / "orders.csv").exists(),
                                reason="run src/clean_data.py first")


def test_one_review_per_order():
    r = pd.read_csv(PROCESSED_DIR / "order_reviews.csv")
    assert r.order_id.is_unique


def test_every_product_category_translated():
    p = pd.read_csv(PROCESSED_DIR / "products.csv")
    c = pd.read_csv(PROCESSED_DIR / "product_categories.csv")
    assert p.product_category_name.notna().all()
    assert set(p.product_category_name) <= set(c.product_category_name)


def test_no_business_rows_dropped():
    rep = json.loads((PROCESSED_DIR / "cleaning_report.json").read_text())
    assert rep["output_rows"]["orders"] == rep["orders"]["rows"] == 99441
    assert rep["output_rows"]["order_items"] == 112650
    assert rep["output_rows"]["order_payments"] == 103886


def test_anomaly_flags_are_booleans_and_consistent():
    o = pd.read_csv(PROCESSED_DIR / "orders.csv")
    flags = [c for c in o.columns if c.startswith("flag_")]
    assert (o[flags].any(axis=1) == o.has_timestamp_anomaly).all()


def test_zip_prefix_zero_padded():
    c = pd.read_csv(PROCESSED_DIR / "customers.csv", dtype=str)
    assert c.customer_zip_code_prefix.str.len().eq(5).all()
