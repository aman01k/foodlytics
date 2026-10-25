"""Load raw CSVs (as TEXT) into schema raw, apply sql/schema.sql, load cleaned CSVs
into schema clean, then (re)build the analytics layer."""
from __future__ import annotations

import csv
import sys

import psycopg

from config.settings import PROCESSED_DIR, RAW_DIR, SQL_DIR, db_url

RAW_TABLES = {
    "olist_customers_dataset": "customers", "olist_geolocation_dataset": "geolocation",
    "olist_order_items_dataset": "order_items", "olist_order_payments_dataset": "order_payments",
    "olist_order_reviews_dataset": "order_reviews", "olist_orders_dataset": "orders",
    "olist_products_dataset": "products", "olist_sellers_dataset": "sellers",
    "product_category_name_translation": "product_category_name_translation",
}
# Load order respects foreign keys.
CLEAN_ORDER = ["geolocation", "customers", "sellers", "product_categories", "products",
               "orders", "order_items", "order_payments", "order_reviews"]


def connect() -> psycopg.Connection:
    return psycopg.connect(db_url().replace("postgresql+psycopg://", "postgresql://"))


def copy_csv(cur, table: str, path, columns: list[str] | None = None) -> None:
    cols = f"({', '.join(columns)})" if columns else ""
    with open(path, "rb") as f, cur.copy(f"COPY {table} {cols} FROM STDIN WITH (FORMAT csv, HEADER true)") as cp:
        while chunk := f.read(1 << 20):
            cp.write(chunk)


def load_raw(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
        for fname, tname in RAW_TABLES.items():
            path = RAW_DIR / f"{fname}.csv"
            with open(path, newline="", encoding="utf-8") as f:
                header = next(csv.reader(f))
            cols = ", ".join(f'"{c}" TEXT' for c in header)
            cur.execute(f"DROP TABLE IF EXISTS raw.{tname}")
            cur.execute(f"CREATE TABLE raw.{tname} ({cols})")
            copy_csv(cur, f"raw.{tname}", path)
    conn.commit()


def load_clean(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS analytics CASCADE")  # views depend on clean tables
        cur.execute((SQL_DIR / "schema.sql").read_text())
        for t in CLEAN_ORDER:
            path = PROCESSED_DIR / f"{t}.csv"
            with open(path, newline="", encoding="utf-8") as f:
                header = next(csv.reader(f))
            copy_csv(cur, f"clean.{t}", path, header)
    conn.commit()


def build_analytics(conn) -> None:
    with conn.cursor() as cur:
        cur.execute((SQL_DIR / "analytical_views.sql").read_text())
    conn.commit()


def main(skip_analytics: bool = False) -> None:
    with connect() as conn:
        load_raw(conn)
        load_clean(conn)
        if not skip_analytics and (SQL_DIR / "analytical_views.sql").exists():
            build_analytics(conn)
        with conn.cursor() as cur:
            for sch in ("raw", "clean"):
                cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=%s ORDER BY 1", (sch,))
                for (t,) in cur.fetchall():
                    cur.execute(f"SELECT count(*) FROM {sch}.{t}")
                    print(f"{sch}.{t}: {cur.fetchone()[0]:,}")


if __name__ == "__main__":
    main(skip_analytics="--no-analytics" in sys.argv)
