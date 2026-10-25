"""Generate and execute the two analysis notebooks (so they always reflect the
current pipeline). Run from the repo root: python notebooks/build_notebooks.py"""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

HERE = Path(__file__).resolve().parent
SETUP = """import sys, json; from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()
sys.path.insert(0, str(ROOT))
import pandas as pd, numpy as np, matplotlib.pyplot as plt
from src.db import query
pd.set_option('display.width', 160); pd.set_option('display.max_columns', 20)
plt.rcParams.update({'figure.figsize': (10, 4), 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.prop_cycle': plt.cycler(color=['#2a78d6', '#eb6834', '#1baf7a'])})"""


def md(s): return nbf.v4.new_markdown_cell(s)
def code(s): return nbf.v4.new_code_cell(s)


EDA = [
    md("# Foodlytics - exploratory analysis\nOlist Brazilian e-commerce data used as a **proxy** for a "
       "food-delivery platform. All numbers below are computed live from the PostgreSQL analytics layer."),
    code(SETUP),
    md("## 1. Raw data profile\nRow counts by layer show nothing was dropped between raw and clean "
       "(except duplicate geolocation points and superseded reviews)."),
    code("""q = " UNION ALL ".join(f"SELECT '{s}.{t}' AS tbl, COUNT(*) AS n FROM {s}.{t}" for s in ['raw','clean']
      for t in ['orders','order_items','order_payments','order_reviews','customers','products','sellers','geolocation'])
query(q)"""),
    code("json.loads((ROOT/'data/processed/cleaning_report.json').read_text())['orders']"),
    md("## 2. Is the business growing?"),
    code("""m = query("SELECT * FROM analytics.v_kpi_monthly")
fig, ax = plt.subplots(1, 2, figsize=(12, 4))
ax[0].bar(m.month, m.valid_orders, width=20); ax[0].set_title('Valid orders per month')
ax[1].plot(m.month, m.aov, marker='o'); ax[1].set_ylim(0); ax[1].set_title('AOV (BRL)')
plt.tight_layout(); query("SELECT * FROM analytics.v_yoy_growth")"""),
    md("Orders +137% YoY (Jan-Aug) while AOV is flat (+0.4%): growth is volume-driven."),
    code("query(open(ROOT/'sql/revenue_analysis.sql').read().split('-- name: a04_gmv_drivers')[1].split('-- name:')[0])"),
    md("## 3. Delivery vs review score (association)"),
    code("query('SELECT * FROM analytics.v_delivery_vs_review')"),
    md("## 4. Customers: repeat behaviour and cohorts"),
    code("query('SELECT * FROM analytics.v_customer_overview').T"),
    code("""c = query("SELECT * FROM analytics.v_cohort_retention WHERE months_since_first BETWEEN 1 AND 12")
piv = c.pivot(index='cohort_month', columns='months_since_first', values='retention_rate') * 100
fig, ax = plt.subplots(figsize=(10, 6)); im = ax.imshow(piv.values, cmap='Blues', aspect='auto')
ax.set_yticks(range(len(piv)), [str(d)[:7] for d in piv.index]); ax.set_xticks(range(12), [f'M{k}' for k in piv.columns])
plt.colorbar(im, label='% of cohort active'); ax.set_title('Cohort retention (blank = not observable)'); plt.show()"""),
    code("query('SELECT * FROM analytics.v_repeat_within_days')"),
    code("query('SELECT * FROM analytics.v_customer_segments')"),
    md("## 5. Categories"),
    code("query('SELECT category, gmv, gmv_share, cumulative_gmv_share, avg_review, on_time_rate, gmv_yoy_growth "
         "FROM analytics.v_category_performance LIMIT 15')"),
    code("query('SELECT * FROM analytics.v_seller_concentration')"),
]

EXP = [
    md("# Discount A/B test - SYNTHETIC experiment analysis\n> **Everything outcome-related in this notebook "
       "is simulated.** Olist contains no randomized promotion. Historical data only calibrates the control arm "
       "(baseline conversion via a back-test, order values via resampling). The treatment effect is an assumption."),
    code(SETUP + "\nfrom dataclasses import replace\nfrom src.experiment_simulator import ExperimentConfig, load_calibration\n"
         "from src.experiment_analysis import analyze, monte_carlo, sample_size, break_even"),
    md("## 1. Calibration (observed back-test at 2018-07-01)"),
    code("cal = load_calibration(); {k: v for k, v in cal.items() if k != 'order_values'}"),
    md("## 2. Pre-registered plan\n* Primary metric: contribution profit per eligible customer (60 days)\n"
       "* Secondary: conversion rate; guardrails: AOV, discount cost\n* α = 0.05 two-sided, target power 80%"),
    code("cfg = ExperimentConfig(); r = analyze(cfg, cal); r['config']"),
    code("r['groups']"),
    code("r['conversion']"),
    code("r['contribution_per_eligible']"),
    code("r['decision']"),
    md("## 3. Break-even and sensitivity (closed form, no simulation noise)"),
    code("r['break_even']"),
    code("r['sensitivity']['sens_margin_x_discount'].pivot(index='contribution_margin', columns='discount_pct', values='break_even_rel_lift').round(2)"),
    code("r['sensitivity']['sens_breakeven_discount']"),
    md("## 4. Power"),
    code("pd.DataFrame(r['power']['sample_size_table'])"),
    code("{k: v for k, v in r['power'].items() if k != 'sample_size_table'}"),
    md("## 5. How do conclusions change with the assumptions?"),
    code("""rows = []
for el in [0.5, 1.5, 5, 15, 30]:
    for mult in [1, 8]:
        c = replace(cfg, price_elasticity=el, n_eligible=int(cal['eligible_population'] * mult))
        x = analyze(c, cal, n_boot=0)
        rows.append({'elasticity': el, 'assumed_rel_lift': c.relative_lift, 'n_eligible': c.n_eligible,
                     'conv_p': round(x['conversion']['p_value'], 4),
                     'profit_diff_per_eligible': round(x['contribution_per_eligible']['diff'], 4),
                     'decision': x['decision']['outcome_code']})
pd.DataFrame(rows)"""),
    md("## 6. Monte Carlo (200 re-runs of the default design)"),
    code("mc = pd.read_csv(ROOT/'reports/results/experiment_monte_carlo.csv'); mc.outcome_code.value_counts(normalize=True)"),
]


def build(cells, name):
    nb = nbf.v4.new_notebook(); nb.cells = cells
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(HERE)}}).execute()
    nbf.write(nb, HERE / name)
    print("wrote", name)


if __name__ == "__main__":
    build(EDA, "exploratory_analysis.ipynb")
    build(EXP, "experiment_analysis.ipynb")
