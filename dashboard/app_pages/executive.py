import streamlit as st

from dashboard import queries as q
from dashboard.ui import brl, cached, card, filters, header, kpi, pal, pct, plot, px, window_badges

start, end, state = filters()
header("Executive overview", ":material/monitoring:",
       "Valid orders only unless stated. Hover the ⓘ icons for metric definitions.",
       window_badges(start, end, state))

k = cached("kpis", start, end, state)
m = cached("monthly", start, end, state)
prev = k["prev"]

# Deltas: vs the preceding period of equal length when it exists, otherwise last month vs the month before.
if prev is not None:
    desc = f"vs {prev['period'][0]:%b %Y}–{prev['period'][1]:%b %Y}"
    base = prev
else:
    desc = f"{m.month.iloc[-1]:%b %Y} vs {m.month.iloc[-2]:%b %Y}" if len(m) > 1 else None
    last, before = m.iloc[-1], m.iloc[-2] if len(m) > 1 else m.iloc[-1]
    base = None


def growth(col_cur, col_m):
    if base is not None:
        return f"{100 * (k[col_cur] / base[col_cur] - 1):+.1f}%"
    return f"{100 * (last[col_m] / before[col_m] - 1):+.1f}%"


def pp(col_cur, col_m, d=2):
    if base is not None:
        return f"{100 * (k[col_cur] - base[col_cur]):+.{d}f} pp"
    return f"{100 * (last[col_m] - before[col_m]):+.{d}f} pp"


with st.container(horizontal=True):
    kpi("Valid orders", f"{int(k['valid_orders']):,}", growth("valid_orders", "valid_orders"),
              delta_description=desc, chart_data=m.valid_orders.tolist(), chart_type="bar",
              help=q.DEFINITIONS["orders"], icon=":material/shopping_bag:")
    kpi("GMV", brl(k["gmv"]), growth("gmv", "gmv"), hero=True, delta_description=desc,
              chart_data=m.gmv.tolist(), chart_type="area", help=q.DEFINITIONS["gmv"], icon=":material/payments:")
    kpi("Average order value", brl(k["aov"], 2), growth("aov", "aov"), delta_description=desc,
              chart_data=m.aov.round(2).tolist(), chart_type="line", help=q.DEFINITIONS["aov"],
              icon=":material/receipt_long:")
with st.container(horizontal=True):
    kpi("Cancellation rate", pct(k["cancellation_rate"], 2), pp("cancellation_rate", "cancellation_rate"),
              delta_color="inverse", delta_description=desc,
              chart_data=m.cancellation_rate.round(5).tolist(), chart_type="line",
              help=q.DEFINITIONS["cancel"], icon=":material/cancel:")
    kpi("Failed-order rate", pct(k["failed_order_rate"], 2), pp("failed_order_rate", "failed_order_rate"),
              delta_color="inverse", delta_description=desc,
              chart_data=m.failed_order_rate.round(5).tolist(), chart_type="line",
              help=q.DEFINITIONS["failed"], icon=":material/report:")
    kpi("On-time delivery", pct(k["on_time_rate"]), pp("on_time_rate", "on_time_rate", 1),
              delta_description=desc, chart_data=m.on_time_rate.round(4).tolist(),
              chart_type="area", help=q.DEFINITIONS["on_time"], icon=":material/local_shipping:")

ins = cached("insights")
with st.container(key="card-takeaways"):
    st.subheader("Key takeaways", icon=":material/lightbulb:")
    st.caption("Computed live across the full analysis window, independent of the filters above.")
    c1, c2, c3 = st.columns(3)
    c1.markdown(f":material/trending_up: **Orders {pct(ins['orders_yoy'], 0)} YoY** "
                f"(Jan–Aug 2018 vs 2017), while AOV moved only {pct(ins['aov_yoy'], 1)}. "
                f"Growth is volume-driven: order volume explains {pct(ins['volume_share'], 0)} of monthly GMV swings.")
    c2.markdown(f":material/star_half: **Late deliveries average {ins['review_late']:.2f}★** "
                f"vs {ins['review_on_time']:.2f}★ on time. That is the largest experience gap in the data "
                "(an association, not proven causation).")
    c3.markdown(f":material/replay: **Only {pct(ins['repeat_rate'], 2)} of customers** returned on a second day. "
                "The platform is acquisition-led, so retention is the key structural weakness.")

left, right = st.columns(2)
with left:
    with card("Monthly trend", ":material/show_chart:"):
        metric = st.segmented_control("Metric", ["Orders", "GMV", "AOV"], default="Orders",
                                      label_visibility="collapsed", required=True)
        col, lab = {"Orders": ("valid_orders", "Valid orders"), "GMV": ("gmv", "GMV (BRL)"),
                    "AOV": ("aov", "AOV (BRL)")}[metric]
        if metric == "AOV":
            fig = px.line(m, x="month", y=col, markers=True, labels={col: lab, "month": ""})
            fig.update_yaxes(rangemode="tozero")
        else:
            fig = px.bar(m, x="month", y=col, labels={col: lab, "month": ""})
        plot(fig, alt=f"{lab} per month", legend=False, height=300)
with right:
    with card("What moved GMV month-on-month?", ":material/stacked_bar_chart:",
              "ΔGMV = ΔOrders×AOV(prev) + ΔAOV×Orders(prev) + interaction. Full window, all states."):
        d = cached("gmv_decomposition", start, end)
        dd = d.melt("month", ["volume_effect", "value_effect", "interaction_effect"], var_name="driver",
                    value_name="brl")
        dd["driver"] = dd.driver.map({"volume_effect": "Order volume", "value_effect": "Order value (AOV)",
                                      "interaction_effect": "Interaction"})
        fig = px.bar(dd, x="month", y="brl", color="driver", labels={"brl": "Change in GMV (BRL)", "month": ""})
        fig.update_layout(barmode="relative")
        plot(fig, alt="Monthly GMV change decomposed into volume, value and interaction effects", height=300)

left, right = st.columns(2)
with left:
    with card("Cancellation rates", ":material/block:"):
        mm = m.melt("month", ["cancellation_rate", "failed_order_rate"], var_name="metric", value_name="rate")
        mm["metric"] = mm.metric.map({"cancellation_rate": "Canceled", "failed_order_rate": "Canceled + unavailable"})
        fig = px.line(mm, x="month", y="rate", color="metric", markers=True,
                      labels={"rate": "Share of orders", "month": ""})
        fig.update_yaxes(tickformat=".1%", rangemode="tozero")
        plot(fig, alt="Monthly cancellation and failed-order rates", height=300)
with right:
    with card("Review score vs delivery timing", ":material/reviews:",
              "Association, not causation. Full window, all states."):
        dv = cached("delivery_vs_review")
        dv["label"] = dv.delivery_bucket.str[3:]
        fig = px.bar(dv, x="label", y="avg_review_score", text_auto=".2f",
                     labels={"avg_review_score": "Avg review (1–5)", "label": ""},
                     hover_data={"orders": ":,", "share_1_2_star": ":.1%", "label": False})
        fig.update_traces(marker_color=[pal()["series"][0]] * 3 + [pal()["series"][1]] * 3, textposition="outside")
        fig.update_yaxes(range=[0, 5.2])
        plot(fig, alt="Average review score by delivery timing bucket", legend=False, height=300)

with st.expander("Monthly KPI table", icon=":material/table_chart:"):
    st.dataframe(m, hide_index=True, alt="Monthly KPI table", column_config={
        "month": st.column_config.DateColumn("Month", format="MMM YYYY"),
        "valid_orders": st.column_config.NumberColumn("Valid orders", format="localized"),
        "gmv": st.column_config.NumberColumn("GMV (R$)", format="localized"),
        "aov": st.column_config.NumberColumn("AOV (R$)", format="%.2f"),
        "cancellation_rate": st.column_config.NumberColumn("Cancel rate", format="percent"),
        "failed_order_rate": st.column_config.NumberColumn("Failed rate", format="percent"),
        "on_time_rate": st.column_config.ProgressColumn("On-time", format="percent", min_value=0, max_value=1),
        "avg_review": st.column_config.NumberColumn("Avg review", format="%.2f ★"),
    })
