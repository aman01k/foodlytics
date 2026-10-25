"""One command to rebuild everything from raw CSVs:
    python run_pipeline.py            # full run
    python run_pipeline.py --skip-download
Steps: ingest -> clean -> load raw/clean + analytics views -> DQ checks ->
Module A-C queries -> experiment calibration + simulation -> opportunity sizing.
"""
from __future__ import annotations

import sys
import time

from src import (clean_data, experiment_analysis, experiment_simulator, ingestion, load_postgres,
                 metrics, opportunity_sizing, validate_data)


def step(name, fn, *a, **kw):
    t = time.time()
    print(f"\n=== {name} ===")
    out = fn(*a, **kw)
    print(f"--- {name} done in {time.time() - t:.1f}s")
    return out


def main() -> int:
    if "--skip-download" not in sys.argv and step("1. ingest", ingestion.main) != 0:
        return 1
    step("2. clean", clean_data.main)
    step("3. load PostgreSQL + build analytics layer", load_postgres.main)
    if step("4. data-quality checks", validate_data.main) != 0:
        print("Data-quality checks FAILED - stopping.")
        return 1
    step("5. Module A-C analyses", metrics.main)
    step("6a. experiment calibration (historical back-test)", experiment_simulator.calibrate)
    step("6b. experiment simulation + statistics (SYNTHETIC)", experiment_analysis.main)
    step("7. opportunity sizing", opportunity_sizing.main)
    print("\nPipeline complete. Dashboard: streamlit run dashboard/app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
