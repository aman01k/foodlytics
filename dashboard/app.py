"""Foodlytics - Streamlit BI dashboard (entry point).

Run from the repo root:  streamlit run dashboard/app.py
Every figure is queried live from PostgreSQL (analytics schema) through
dashboard/queries.py; the experiment page re-runs the SYNTHETIC simulator.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import streamlit as st  # noqa: E402

from dashboard.ui import cached  # noqa: E402

st.set_page_config(page_title="Foodlytics", page_icon=str(HERE / "assets" / "icon.svg"), layout="wide")
st.logo(str(HERE / "assets" / "logo.svg"), icon_image=str(HERE / "assets" / "icon.svg"), size="large")

pages = {
    "Performance": [
        st.Page(HERE / "app_pages" / "executive.py", title="Executive overview", icon=":material/monitoring:",
                default=True),
        st.Page(HERE / "app_pages" / "customers.py", title="Customer intelligence", icon=":material/group:"),
        st.Page(HERE / "app_pages" / "categories.py", title="Category performance", icon=":material/category:"),
    ],
    "Decisions": [
        st.Page(HERE / "app_pages" / "experiment.py", title="Discount experiment", icon=":material/science:"),
        st.Page(HERE / "app_pages" / "opportunities.py", title="Opportunity sizing", icon=":material/target:"),
    ],
}
nav = st.navigation(pages)

with st.sidebar:
    st.caption("FILTERS")
    months = cached("months")
    start, end = st.select_slider("Purchase month", options=months, value=(months[0], months[-1]),
                                  format_func=lambda m: m.strftime("%b %Y"))
    state = st.selectbox("Customer state", cached("states"))
    st.session_state["filters"] = {"start": start, "end": end, "state": state}
    st.caption(f"Analysis window {months[0]:%b %Y} – {months[-1]:%b %Y}. The 2016 ramp-up and the "
               "Sep–Oct 2018 data cut-off are excluded. Currency: BRL.")
    st.caption("Built on the Olist Brazilian e-commerce dataset as a **proxy** for food delivery. "
               "It is not Swiggy or food-delivery data.")

nav.run()
