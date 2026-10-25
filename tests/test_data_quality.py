"""Every SQL data-quality check must pass (PK uniqueness, FK integrity,
critical nulls, raw-vs-clean reconciliation, no join fan-out, revenue reconciliation,
cohort integrity)."""
import pytest

from config.settings import SQL_DIR
from src.db import named_queries
from tests.conftest import needs_db

CHECKS = named_queries(SQL_DIR / "cleaning_and_validation.sql")


@needs_db
@pytest.mark.parametrize("name", list(CHECKS))
def test_quality_check(name):
    from src.db import query
    row = query(CHECKS[name]).iloc[0]
    assert int(row.iloc[1]) == 0, f"{name}: {row.iloc[2]}"
