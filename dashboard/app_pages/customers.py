import plotly.graph_objects as go
import streamlit as st

from dashboard import queries as q
from dashboard.ui import brl, cached, card, filters, header, kpi, pal, pct, plot, px, window_badges

start, end, state = filters()
header("Customer intelligence", ":material/group:",
       "Customer = customer_unique_id, an account proxy (Olist's customer_id is per order). "
       "Frequency counts distinct purchase days, so same-day split baskets are not repeats.",
       window_badges(start, end, "All")[:1] + [("Snapshot 2018-09-01", "gray", ":material/event:")])

seg = st.selectbox("Customer segment", cached("segments"), help="Mutually exclusive, rule-based segments.")
o = cached("customer_overview", seg)
t = cached("segment_thresholds")
with st.container(horizontal=True):
    kpi("Customers", f"{int(o['customers']):,}", icon=":material/person:")
    kpi("Repeat rate", pct(o["repeat_rate"], 2), help=q.DEFINITIONS["repeat"],
              icon=":material/replay:")
    kpi("Avg lifetime GMV", brl(o["avg_gmv"], 2), icon=":material/savings:")
    kpi("Avg recency", f"{o['avg_recency']:.0f} days", icon=":material/schedule:",
              help="Days from the last valid purchase to the 2018-09-01 snapshot.")
st.caption(f"Segment rules: high-value means lifetime GMV ≥ {brl(t['high_value_gmv_threshold'], 2)} (top 20%). "
           f"Potentially inactive means no purchase in {int(t['inactive_days'])} days; this is not a validated churn label. "
           f"The median gap between purchases is {t['median_gap_days']:.0f} days and the 75th percentile is {t['p75_gap_days']:.0f}.")

with card("Cohort retention", ":material/grid_on:",
          q.DEFINITIONS["retention"] + " Month 0 (always 100%) is omitted so the scale stays readable."):
    cm = cached("cohort_matrix", 12)
    piv = cm.pivot(index="cohort_month", columns="months_since_first", values="retention_rate").drop(columns=0)
    sizes = cm.drop_duplicates("cohort_month").set_index("cohort_month").cohort_size
    ylab = [f"{d:%b %Y}  ·  n={sizes[d]:,}" for d in piv.index]
    fig = go.Figure(go.Heatmap(z=piv.values * 100, x=[f"M{k}" for k in piv.columns], y=ylab, colorscale=pal()["seq"],
                               zmin=0, colorbar=dict(title="%", thickness=10), xgap=2, ygap=2,
                               hovertemplate="%{y}<br>%{x}: %{z:.2f}% active<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    plot(fig, alt="Monthly cohort retention heatmap", legend=False, height=520, hover="closest")

left, right = st.columns(2)
with left:
    with card("New vs returning customers", ":material/person_add:"):
        nv = cached("new_vs_returning", start, end).melt("month", var_name="type", value_name="customers")
        nv["type"] = nv.type.map({"new_customers": "New", "returning_customers": "Returning"})
        fig = px.bar(nv, x="month", y="customers", color="type", labels={"month": "", "customers": "Customers"})
        plot(fig, alt="New versus returning customers per month", height=320)
with right:
    with card("Segments: share of customers vs GMV", ":material/donut_large:"):
        sg = cached("segment_table")
        long = sg.melt("segment", ["share_customers", "share_gmv"], var_name="m", value_name="share")
        long["m"] = long.m.map({"share_customers": "Customers", "share_gmv": "GMV"})
        long["segment"] = long.segment.str[3:]
        fig = px.bar(long, y="segment", x="share", color="m", barmode="group", orientation="h",
                     labels={"segment": "", "share": ""})
        fig.update_xaxes(tickformat=".0%")
        fig.update_yaxes(autorange="reversed")
        plot(fig, alt="Share of customers and GMV by segment", height=320, hover="y unified")

left, right = st.columns(2)
with left:
    with card("Purchase frequency", ":material/bar_chart:", "Distinct purchase days (5 = 5+). Log scale."):
        f = cached("frequency")
        fig = px.bar(f, x="purchase_days_capped", y="customers", log_y=True,
                     labels={"purchase_days_capped": "Purchase days", "customers": "Customers"},
                     hover_data={"share": ":.2%"})
        plot(fig, alt="Customers by number of purchase days", legend=False, height=300)
with right:
    with card("Days between purchases", ":material/timelapse:", "Gaps between consecutive purchase days."):
        g = cached("purchase_gaps")
        fig = px.histogram(g, x="gap_days", nbins=40, labels={"gap_days": "Days"})
        fig.update_yaxes(title="Repeat purchases")
        plot(fig, alt="Histogram of days between consecutive purchases", legend=False, height=300)

with card("Repeat purchase within N days", ":material/hourglass_bottom:",
          "Only customers with a full N-day observation window are included, which handles right-censoring."):
    rw = cached("repeat_within_days")
    st.dataframe(rw, hide_index=True, alt="Repeat rate within N days of first purchase", column_config={
        "horizon_days": st.column_config.NumberColumn("Horizon (days)"),
        "eligible_customers": st.column_config.NumberColumn("Customers observed", format="localized"),
        "repeat_rate": st.column_config.ProgressColumn("Repeat rate", format="percent", min_value=0, max_value=0.05),
    })
