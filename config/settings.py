"""Central configuration: paths, DB connection, analysis parameters.

DB credentials come from environment variables (or a local .env file that is
git-ignored). Nothing secret is stored in the repository.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
SQL_DIR = ROOT / "sql"
REPORTS_DIR = ROOT / "reports"
RESULTS_DIR = ROOT / "reports" / "results"


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def db_url() -> str:
    user = quote_plus(os.environ.get("PGUSER", os.environ.get("USER", "postgres")))
    pwd = quote_plus(os.environ.get("PGPASSWORD", ""))  # hosted DB passwords often contain @, #, /
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    db = os.environ.get("PGDATABASE", "foodlytics")
    sslmode = os.environ.get("PGSSLMODE")  # e.g. "require" for Supabase/Neon
    auth = f"{user}:{pwd}" if pwd else user
    query = f"?sslmode={sslmode}" if sslmode else ""
    return f"postgresql+psycopg://{auth}@{host}:{port}/{db}{query}"


# ---- Analytical definitions (documented in reports/metric_definitions.md) ----
# Orders in these statuses are "completed" for revenue purposes.
COMPLETED_STATUSES = ("delivered",)
# 'canceled' and 'unavailable' count as unsuccessful orders.
CANCELLED_STATUSES = ("canceled", "unavailable")

# RFM / segmentation parameters
RFM_SNAPSHOT_BUFFER_DAYS = 1      # snapshot = last order date + 1 day
INACTIVE_RECENCY_DAYS = 180       # "potentially inactive" threshold (no churn label)

# Experiment defaults live in config/experiment.json-like dict in src/experiment_simulator.py
RANDOM_SEED = 42
