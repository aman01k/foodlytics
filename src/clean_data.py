"""Raw Olist CSVs -> cleaned, typed CSVs in data/processed/ + cleaning_report.json.

Principles
- Never silently drop business records. Anomalies are FLAGGED; derived metrics
  are nulled in the analytics layer when a flagged value would make them invalid.
- The only rows removed are exact duplicates (geolocation) and superseded
  reviews (we keep one review per order: the most recently answered).
- Every decision is counted in the report so it can be quoted in documentation.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config.settings import PROCESSED_DIR, RAW_DIR

ORDER_TS = ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
            "order_delivered_customer_date", "order_estimated_delivery_date"]

# Two categories present in products but absent from the official translation file.
EXTRA_TRANSLATIONS = {
    "pc_gamer": "pc_gamer",
    "portateis_cozinha_e_preparadores_de_alimentos": "portable_kitchen_and_food_preparers",
    "unknown": "unknown",
}

# Rough bounding box of Brazil, used to reject geolocation outliers.
BR_LAT, BR_LNG = (-34.0, 6.0), (-74.0, -34.0)


def _read(name: str, **kw) -> pd.DataFrame:
    return pd.read_csv(RAW_DIR / f"{name}.csv", **kw)


def clean_customers(rep: dict) -> pd.DataFrame:
    df = _read("olist_customers_dataset", dtype=str)
    df["customer_city"] = df["customer_city"].str.strip().str.lower()
    df["customer_state"] = df["customer_state"].str.strip().str.upper()
    df["customer_zip_code_prefix"] = df["customer_zip_code_prefix"].str.zfill(5)
    rep["customers"] = {
        "rows": len(df),
        "customer_id_unique": bool(df.customer_id.is_unique),
        "distinct_customer_unique_id": int(df.customer_unique_id.nunique()),
        "customer_ids_per_unique_id>1": int((df.groupby("customer_unique_id").size() > 1).sum()),
    }
    return df


def clean_orders(rep: dict) -> pd.DataFrame:
    df = _read("olist_orders_dataset")
    for c in ORDER_TS:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["order_status"] = df["order_status"].str.strip().str.lower()

    delivered = df["order_status"].eq("delivered")
    df["flag_delivered_missing_date"] = delivered & df["order_delivered_customer_date"].isna()
    df["flag_deliv_date_not_delivered"] = ~delivered & df["order_delivered_customer_date"].notna()
    df["flag_carrier_before_approval"] = df["order_delivered_carrier_date"] < df["order_approved_at"]
    df["flag_carrier_before_purchase"] = df["order_delivered_carrier_date"] < df["order_purchase_timestamp"]
    df["flag_delivered_before_carrier"] = (df["order_delivered_customer_date"]
                                           < df["order_delivered_carrier_date"])
    df["flag_delivered_before_purchase"] = (df["order_delivered_customer_date"]
                                            < df["order_purchase_timestamp"])
    flags = [c for c in df.columns if c.startswith("flag_")]
    for c in flags:
        df[c] = df[c].fillna(False).astype(bool)
    df["has_timestamp_anomaly"] = df[flags].any(axis=1)
    rep["orders"] = {
        "rows": len(df),
        "status_counts": df.order_status.value_counts().to_dict(),
        "purchase_min": str(df.order_purchase_timestamp.min()),
        "purchase_max": str(df.order_purchase_timestamp.max()),
        **{c: int(df[c].sum()) for c in flags},
        "rows_with_any_timestamp_anomaly": int(df.has_timestamp_anomaly.sum()),
        "missing_approved_at": int(df.order_approved_at.isna().sum()),
        "missing_carrier_date": int(df.order_delivered_carrier_date.isna().sum()),
        "missing_delivered_date": int(df.order_delivered_customer_date.isna().sum()),
    }
    return df


def clean_items(rep: dict) -> pd.DataFrame:
    df = _read("olist_order_items_dataset")
    df["shipping_limit_date"] = pd.to_datetime(df["shipping_limit_date"], errors="coerce")
    rep["order_items"] = {
        "rows": len(df),
        "duplicate_pk": int(df.duplicated(["order_id", "order_item_id"]).sum()),
        "price_le_0": int((df.price <= 0).sum()),
        "freight_lt_0": int((df.freight_value < 0).sum()),
        "freight_zero": int((df.freight_value == 0).sum()),
    }
    return df


def clean_payments(rep: dict) -> pd.DataFrame:
    df = _read("olist_order_payments_dataset")
    df["flag_zero_value"] = df["payment_value"] <= 0
    df["flag_invalid_installments"] = df["payment_installments"] < 1
    rep["order_payments"] = {
        "rows": len(df),
        "duplicate_pk": int(df.duplicated(["order_id", "payment_sequential"]).sum()),
        "zero_value_rows": int(df.flag_zero_value.sum()),
        "invalid_installments_rows": int(df.flag_invalid_installments.sum()),
        "payment_type_counts": df.payment_type.value_counts().to_dict(),
    }
    return df


def clean_reviews(rep: dict) -> pd.DataFrame:
    df = _read("olist_order_reviews_dataset")
    for c in ["review_creation_date", "review_answer_timestamp"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    n0 = len(df)
    df = (df.sort_values(["order_id", "review_answer_timestamp", "review_creation_date"])
            .drop_duplicates("order_id", keep="last"))
    rep["order_reviews"] = {
        "raw_rows": n0, "kept_rows": len(df), "superseded_reviews_dropped": n0 - len(df),
        "review_id_repeated_across_orders_in_raw": True,
        "rule": "one review per order: latest review_answer_timestamp",
    }
    return df.drop(columns=["review_comment_title", "review_comment_message"])  # free text unused


def clean_products(rep: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = _read("olist_products_dataset")
    df = df.rename(columns={"product_name_lenght": "product_name_length",
                            "product_description_lenght": "product_description_length"})
    tr = _read("product_category_name_translation")
    tr = pd.concat([tr, pd.DataFrame(list(EXTRA_TRANSLATIONS.items()), columns=tr.columns)],
                   ignore_index=True).drop_duplicates("product_category_name")
    n_missing_cat = int(df.product_category_name.isna().sum())
    df["product_category_name"] = df["product_category_name"].fillna("unknown")
    zero_w = df.product_weight_g.eq(0)
    df.loc[zero_w, "product_weight_g"] = np.nan  # 0 g is physically impossible
    for c in ["product_name_length", "product_description_length", "product_photos_qty"]:
        df[c] = df[c].astype("Int64")  # keep integers integer despite NaN
    untranslated = set(df.product_category_name) - set(tr.product_category_name)
    rep["products"] = {
        "rows": len(df), "missing_category_set_to_unknown": n_missing_cat,
        "zero_weight_set_null": int(zero_w.sum()),
        "categories_missing_from_translation_file_added_manually": list(EXTRA_TRANSLATIONS)[:2],
        "still_untranslated": sorted(untranslated),
    }
    return df, tr


def clean_sellers(rep: dict) -> pd.DataFrame:
    df = _read("olist_sellers_dataset", dtype=str)
    df["seller_city"] = df["seller_city"].str.strip().str.lower()
    df["seller_state"] = df["seller_state"].str.strip().str.upper()
    df["seller_zip_code_prefix"] = df["seller_zip_code_prefix"].str.zfill(5)
    rep["sellers"] = {"rows": len(df)}
    return df


def clean_geolocation(rep: dict) -> pd.DataFrame:
    df = _read("olist_geolocation_dataset", dtype={"geolocation_zip_code_prefix": str})
    n0 = len(df)
    df["geolocation_zip_code_prefix"] = df["geolocation_zip_code_prefix"].str.zfill(5)
    dups = int(df.duplicated().sum())
    df = df.drop_duplicates()
    inside = (df.geolocation_lat.between(*BR_LAT) & df.geolocation_lng.between(*BR_LNG))
    outliers = int((~inside).sum())
    df = df[inside]
    df["geolocation_city"] = df["geolocation_city"].str.strip().str.lower()
    g = df.groupby("geolocation_zip_code_prefix")
    out = g.agg(lat=("geolocation_lat", "median"), lng=("geolocation_lng", "median"),
                state=("geolocation_state", lambda s: s.mode().iat[0]),
                city=("geolocation_city", lambda s: s.mode().iat[0]),
                n_points=("geolocation_lat", "size")).reset_index()
    out = out.rename(columns={"geolocation_zip_code_prefix": "zip_code_prefix"})
    rep["geolocation"] = {"raw_rows": n0, "exact_duplicates_dropped": dups,
                          "outside_brazil_dropped": outliers,
                          "zip_prefixes_in_output": len(out),
                          "rule": "aggregated to one row per zip prefix (median lat/lng, modal city/state)"}
    return out


def main() -> dict:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    rep: dict = {}
    prod, tr = clean_products(rep)
    tables = {
        "customers": clean_customers(rep), "orders": clean_orders(rep),
        "order_items": clean_items(rep), "order_payments": clean_payments(rep),
        "order_reviews": clean_reviews(rep), "products": prod,
        "product_categories": tr, "sellers": clean_sellers(rep),
        "geolocation": clean_geolocation(rep),
    }
    for name, df in tables.items():
        df.to_csv(PROCESSED_DIR / f"{name}.csv", index=False)
    rep["output_rows"] = {k: len(v) for k, v in tables.items()}
    (PROCESSED_DIR / "cleaning_report.json").write_text(json.dumps(rep, indent=2, default=str))
    print(json.dumps(rep["output_rows"], indent=2))
    return rep


if __name__ == "__main__":
    main()
