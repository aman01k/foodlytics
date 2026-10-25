import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.ui import brl, card, diverging, header, kpi, pal, pct, plot
from src.experiment_analysis import analyze, sample_size
from src.experiment_simulator import ExperimentConfig, load_calibration

header("Discount A/B test", ":material/science:",
       "Should one-time buyers get 10% off their next order? The primary metric is contribution profit per "
       "eligible customer over 60 days.",
       [("Synthetic experiment", "red", ":material/experiment:"),
        ("Control calibrated on a real back-test", "blue", ":material/history:"),
        ("Decision computed, not hardcoded", "green", ":material/rule:")])

cal = load_calibration()
left, right = st.columns([1, 2.4], gap="medium")

with left:
    with st.form("cfg"):
        st.subheader("Assumptions", icon=":material/tune:")
        st.caption("None of these values can be observed in Olist. Change them and re-run.")
        disc = st.slider("Discount", 1, 30, 10, format="%d%%") / 100
        elas = st.slider("Price elasticity of conversion", 0.0, 10.0, 1.5, 0.1,
                         help="Relative conversion lift = elasticity × discount.")
        margin = st.slider("Contribution margin on GMV", 5, 40, 15, format="%d%%") / 100
        vcost = st.slider("Variable cost per order (R$)", 0.0, 10.0, 1.5, 0.5)
        mult = st.select_slider("Eligible population ×", [0.25, 0.5, 1, 2, 4, 8, 16], 1,
                                help=f"1× = {cal['eligible_population']:,} real one-time buyers (31–365 days).")
        seed = st.number_input("Random seed", 0, 10_000, 42)
        st.form_submit_button("Run experiment", icon=":material/play_arrow:", type="primary", width="stretch")
    with st.container(key="card-calibration"):
        st.markdown("**Calibration (observed)**")
        st.caption(f"Back-test at {cal['snapshot']}: {cal['backtest_converted']:,} of {cal['backtest_eligible']:,} "
                   f"eligible buyers purchased within 60 days, a **{pct(cal['baseline_conversion'], 3)}** baseline. "
                   f"Order values are resampled from {len(cal['order_values']):,} real repeat orders.")

cfg = ExperimentConfig(discount_pct=disc, price_elasticity=elas, contribution_margin=margin,
                       variable_cost_per_order=vcost, n_eligible=int(cal["eligible_population"] * mult),
                       seed=int(seed))


@st.cache_data(show_spinner="Simulating experiment…", max_entries=32)
def run(c_: dict):
    r = analyze(ExperimentConfig(**c_), cal, n_boot=300)
    r.pop("data")
    return r


res = run({k: v for k, v in cfg.__dict__.items() if k != "order_values"})
dec, conv, prof = res["decision"], res["conversion"], res["contribution_per_eligible"]

with right:
    color = {1: "green", 2: "red", 3: "orange"}[dec["outcome_code"]]
    icon = {1: ":material/check_circle:", 2: ":material/block:", 3: ":material/warning:"}[dec["outcome_code"]]
    with st.container(key="card-decision"):
        st.badge(f"Outcome {dec['outcome_code']} of 3", color=color, icon=icon)
        head, _, tail = dec["decision"].partition(":")
        st.subheader(head.capitalize())
        st.markdown(f"**{tail.strip().capitalize()}.** {dec['recommended_action']}")
    with st.container(horizontal=True):
        kpi("Control conversion", pct(conv["control_rate"], 3))
        kpi("Treatment conversion", pct(conv["treatment_rate"], 3), f"{100 * conv['abs_lift']:+.3f} pp",
                  help=f"p = {conv['p_value']:.3f} (two-proportion z-test)")
        kpi("Relative lift", pct(conv["rel_lift"]),
                  help=f"95% CI {pct(conv['rel_lift_ci'][0])} to {pct(conv['rel_lift_ci'][1])}")
    with st.container(horizontal=True):
        kpi("Δ contribution / eligible", brl(prof["diff"], 3),
                  help=f"Primary metric. 95% CI {brl(prof['ci'][0], 3)} to {brl(prof['ci'][1], 3)} (Welch); "
                       f"bootstrap {brl(prof['boot_ci'][0], 3)} to {brl(prof['boot_ci'][1], 3)}.")
        kpi("If rolled out to all eligible", brl(res["incremental_contribution_if_rolled_out"]))
        kpi("Break-even relative lift", pct(res["break_even"]["break_even_rel_lift"], 0),
                  help="The lift at which treatment contribution per eligible customer equals control.")

    with card("Treatment − control, with 95% confidence intervals", ":material/straighten:",
              "Each row has its own unit. An interval that crosses 0 means no reliable difference."):
        rows = [("Conversion (pp)", 100 * conv["abs_lift"], [100 * x for x in conv["abs_lift_ci"]]),
                ("Net revenue / eligible (R$)", res["net_revenue_per_eligible"]["diff"],
                 res["net_revenue_per_eligible"]["ci"]),
                ("Contribution / eligible (R$)", prof["diff"], prof["ci"])]
        fig = go.Figure()
        for i, (name, est, (lo, hi)) in enumerate(rows):
            fig.add_trace(go.Scatter(x=[lo, hi], y=[name, name], mode="lines", showlegend=False,
                                     line=dict(color=pal()["series"][i], width=3), hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=[est], y=[name], mode="markers", showlegend=False,
                                     marker=dict(size=12, color=pal()["series"][i], line=dict(color=pal()["mark_gap"], width=2)),
                                     hovertemplate=f"{name}: {est:.4f}<br>95% CI {lo:.4f} to {hi:.4f}<extra></extra>"))
        fig.add_vline(x=0, line_color=pal()["muted"], line_dash="dot")
        plot(fig, alt="Treatment minus control estimates with confidence intervals", legend=False, height=220,
             hover="closest")

left, right = st.columns(2)
with left:
    with card("Profit sensitivity", ":material/grid_view:",
              "Expected incremental contribution per 1,000 eligible customers (closed form, current margin and "
              "cost). Blue = profit, red = loss."):
        sens = res["sensitivity"]["sens_discount_x_lift"]
        pv = sens.pivot(index="discount_pct", columns="relative_lift", values="incr_contribution_per_1000_eligible")
        zmax = float(np.nanmax(np.abs(pv.values)))
        fig = go.Figure(go.Heatmap(z=pv.values, x=[f"{c:.0%}" for c in pv.columns],
                                   y=[f"{i:.0%}" for i in pv.index], colorscale=diverging(), zmid=0, zmin=-zmax,
                                   zmax=zmax, xgap=2, ygap=2, text=np.round(pv.values, 0), texttemplate="%{text}",
                                   colorbar=dict(title="R$", thickness=10),
                                   hovertemplate="Discount %{y}, lift %{x}: R$ %{z:.2f} per 1,000<extra></extra>"))
        fig.update_layout(xaxis_title="True relative conversion lift", yaxis_title="Discount",
                          xaxis_type="category", yaxis_type="category")
        plot(fig, alt="Incremental contribution by discount and lift", legend=False, height=340, hover="closest")
with right:
    with card("Break-even lift", ":material/balance:",
              "The relative conversion lift needed for the discount to pay for itself."):
        be = res["sensitivity"]["sens_margin_x_discount"].pivot(index="contribution_margin", columns="discount_pct",
                                                               values="break_even_rel_lift")
        st.dataframe(be.map(lambda v: "impossible" if not np.isfinite(v) else f"{v:.0%}")
                     .rename(index=lambda i: f"{i:.0%} margin", columns=lambda c: f"{c:.0%} off")
                     .rename_axis(index=None, columns=None),
                     alt="Break-even relative lift by margin and discount")
    pw = res["power"]
    with card("Statistical power", ":material/speed:"):
        with st.container(horizontal=True):
            st.metric("Power now", pct(pw["power_at_actual_n"], 0), border=True)
            st.metric("n / arm for 80%", f"{pw['n_per_arm_needed_for_assumed_lift']:,}", border=True)
            st.metric("Min. detectable lift", pct(pw["mde_rel_lift_at_actual_n"], 0), border=True)
        with st.popover("Sample-size calculator", icon=":material/calculate:"):
            p0 = st.number_input("Baseline conversion", 0.0001, 0.5, float(cal["baseline_conversion"]),
                                 format="%.4f")
            lift = st.number_input("Relative lift to detect", 0.01, 5.0, 0.15)
            st.metric("n per arm (α = 0.05, power = 80%)", f"{sample_size(p0, lift):,}")

with st.expander("Arm-level results table", icon=":material/table_chart:"):
    st.dataframe(pd.DataFrame(res["groups"]), alt="Experiment arm-level results")
