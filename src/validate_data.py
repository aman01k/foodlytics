"""Run every data-quality check in sql/cleaning_and_validation.sql and write a report."""
from __future__ import annotations

import sys

import pandas as pd

from config.settings import RESULTS_DIR, SQL_DIR
from src.db import named_queries, query


def run_checks() -> pd.DataFrame:
    rows = []
    for name, sql in named_queries(SQL_DIR / "cleaning_and_validation.sql").items():
        df = query(sql)
        rows.append({"check_name": name, "failures": int(df.iloc[0, 1]), "detail": df.iloc[0, 2]})
    out = pd.DataFrame(rows)
    out["status"] = out.failures.map(lambda f: "PASS" if f == 0 else "FAIL")
    return out


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = run_checks()
    out.to_csv(RESULTS_DIR / "data_quality_checks.csv", index=False)
    print(out.to_string(index=False))
    return int((out.status == "FAIL").any())


if __name__ == "__main__":
    sys.exit(main())
