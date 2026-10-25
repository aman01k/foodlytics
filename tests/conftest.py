import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _db_ok() -> bool:
    try:
        from src.db import query
        query("SELECT 1 FROM analytics.fct_orders LIMIT 1")
        return True
    except Exception:
        return False


DB_AVAILABLE = _db_ok()
needs_db = pytest.mark.skipif(not DB_AVAILABLE, reason="PostgreSQL analytics schema not available")
