"""Headless smoke tests: every dashboard page renders without exceptions and
shows KPIs computed from the database (streamlit.testing AppTest)."""
import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import ROOT, needs_db

PAGES = ["executive", "customers", "categories", "experiment", "opportunities"]


def _app():
    return AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=180)


@needs_db
@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page):
    at = _app().run()
    at.switch_page(str(ROOT / "dashboard" / "app_pages" / f"{page}.py")).run()
    assert not at.exception, at.exception
    assert at.title[0].value


@needs_db
def test_executive_kpi_matches_sql():
    from src.db import query
    at = _app().run()
    assert not at.exception, at.exception
    expected = query("SELECT valid_orders, gmv FROM analytics.v_kpi_summary").iloc[0]
    assert at.metric[0].value == f"{int(expected.valid_orders):,}"
    assert at.metric[1].value == f"R$ {float(expected.gmv) / 1e6:,.2f}M"
