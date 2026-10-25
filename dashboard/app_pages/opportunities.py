import streamlit as st

from dashboard.ui import brl, cached, card, header, kpi, plot, px
from src.experiment_simulator import ExperimentConfig

dc = ExperimentConfig()
header("Opportunity sizing", ":material/target:",
       "Baselines are observed over the last 12 months (Sep 2017–Aug 2018); targets are scenario assumptions. "
       f"Contribution assumes a {dc.contribution_margin:.0%} margin and R${dc.variable_cost_per_order:.2f} per order, "
       "because Olist has no cost data.",
       [("Scenario analysis, not forecasts", "orange", ":material/insights:"),
        ("Annualised (last 12 months)", "blue", ":material/calendar_month:")])

ot = cached("opportunity_table")
icons = [":material/replay:", ":material/remove_shopping_cart:", ":material/local_shipping:"]
with st.container(horizontal=True):
    for (name, g), icon in zip(ot.groupby("opportunity", sort=True), icons):
        base = g[g.scenario == "base"].iloc[0]
        lo, hi = g.incremental_gmv.min(), g.incremental_gmv.max()
        kpi(name[3:], brl(base.incremental_gmv), icon=icon, key=name[:2].strip('. '),
                  help=f"{base.scenario_assumption}. Range {brl(lo)}–{brl(hi)}. Evidence: {base.evidence_type}.")

with card("Incremental annual GMV by scenario", ":material/bar_chart:"):
    d = ot.assign(label=ot.opportunity.str[3:])
    fig = px.bar(d, x="incremental_gmv", y="label", color="scenario", barmode="group", orientation="h",
                 labels={"incremental_gmv": "Incremental GMV (BRL)", "label": ""},
                 category_orders={"scenario": ["low", "base", "high"]},
                 hover_data={"incremental_contribution": ":,.0f", "scenario_assumption": True, "label": False})
    fig.update_yaxes(autorange="reversed")
    plot(fig, alt="Incremental annual GMV by opportunity and scenario", height=320, hover="y unified")

with card("Assumptions and measurement plans", ":material/fact_check:"):
    st.dataframe(ot, hide_index=True, alt="Opportunity sizing table", column_order=[
        "opportunity", "scenario", "baseline_metric", "scenario_assumption", "population", "affected_units",
        "incremental_gmv", "incremental_contribution", "gmv_pct_of_ltm", "evidence_type", "measurement_plan"],
        column_config={
        "affected_units": st.column_config.NumberColumn("Units affected", format="%.0f"),
        "incremental_gmv": st.column_config.NumberColumn("Δ GMV (R$)", format="localized"),
        "incremental_contribution": st.column_config.NumberColumn("Δ contribution (R$)", format="localized"),
        "gmv_pct_of_ltm": st.column_config.NumberColumn("% of LTM GMV", format="percent"),
        "measurement_plan": st.column_config.TextColumn("Measurement plan", width="large"),
    })
