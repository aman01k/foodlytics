"""Experiment simulator & statistics. Uses a fixed toy calibration so it runs without a DB."""
from dataclasses import replace

import numpy as np
import pytest
from scipy import stats

from src.experiment_analysis import (analyze, break_even, break_even_discount, conversion_test, decide,
                                     expected_incremental, mean_diff_test, sample_size)
from src.experiment_simulator import ExperimentConfig, resolve, simulate

CAL = {"baseline_conversion": 0.05, "eligible_population": 20_000, "extra_orders_rate": 0.0,
       "order_values": [100.0, 120.0, 80.0, 150.0, 50.0], "source": "TEST"}
CFG = ExperimentConfig(seed=7)


def test_assignment_split_is_exact_and_labelled_synthetic():
    df = simulate(CFG, CAL)
    assert len(df) == 20_000
    assert (df.group == "treatment").sum() == 10_000
    assert df.is_synthetic.all() and df.customer_id.str.startswith("SIM-").all()


def test_reproducible_with_seed_and_varies_without():
    a, b = simulate(CFG, CAL), simulate(CFG, CAL)
    c = simulate(replace(CFG, seed=8), CAL)
    assert a.equals(b)
    assert not a.equals(c)


def test_metric_arithmetic():
    df = simulate(CFG, CAL)
    m, cost, d = CFG.contribution_margin, CFG.variable_cost_per_order, CFG.discount_pct
    ctl, trt = df[df.group == "control"], df[df.group == "treatment"]
    assert (ctl.discount_cost == 0).all()
    assert np.allclose(trt.discount_cost, d * trt.gmv, atol=1e-3)
    assert np.allclose(df.contribution, m * df.gmv - cost * df.n_orders - df.discount_cost, atol=1e-3)
    assert ((df.n_orders > 0) == df.converted).all()
    assert (df.gmv[~df.converted] == 0).all()


def test_treatment_effect_recovered_at_large_n():
    cfg = replace(CFG, n_eligible=400_000)
    df = simulate(cfg, CAL)
    r = conversion_test(df)
    assert r["control_rate"] == pytest.approx(0.05, abs=0.002)
    assert r["rel_lift"] == pytest.approx(cfg.relative_lift, abs=0.04)
    assert r["rel_lift_ci"][0] < cfg.relative_lift < r["rel_lift_ci"][1]


def test_conversion_test_matches_manual_z():
    df = simulate(CFG, CAL)
    r = conversion_test(df)
    x = np.array([r["treatment_conversions"], r["control_conversions"]])
    n = np.array([r["n_treatment"], r["n_control"]])
    p = x.sum() / n.sum()
    z = (x[0] / n[0] - x[1] / n[1]) / np.sqrt(p * (1 - p) * (1 / n[0] + 1 / n[1]))
    assert r["z"] == pytest.approx(z)
    assert r["p_value"] == pytest.approx(2 * stats.norm.sf(abs(z)))


def test_mean_diff_ci_and_bootstrap_agree():
    rng = np.random.default_rng(0)
    t, c = rng.exponential(2.0, 5000), rng.exponential(1.8, 5000)
    r = mean_diff_test(t, c, n_boot=500)
    assert r["ci"][0] < r["diff"] < r["ci"][1]
    assert r["boot_ci"][0] == pytest.approx(r["ci"][0], abs=0.03)
    assert r["p_value"] == pytest.approx(stats.ttest_ind(t, c, equal_var=False).pvalue)


@pytest.mark.parametrize("conv_p,lift,ci,code", [
    (0.001, 0.01, (0.02, 0.10), 1),     # profit CI above zero -> launch
    (0.001, 0.01, (-0.10, -0.02), 2),   # conversion up, profit down
    (0.001, 0.01, (-0.05, 0.05), 2),    # conversion up, profit unresolved
    (0.40, 0.01, (-0.05, 0.05), 3),     # nothing reliable
])
def test_decision_rule(conv_p, lift, ci, code):
    d = decide({"p_value": conv_p, "abs_lift": lift}, {"ci": list(ci)})
    assert d["outcome_code"] == code


def test_break_even_is_zero_profit_point():
    rc = resolve(CFG, CAL)
    be = break_even(rc)
    assert expected_incremental(rc, rel_lift=be["break_even_rel_lift"]) == pytest.approx(0, abs=1e-9)
    assert expected_incremental(rc, rel_lift=be["break_even_rel_lift"] + 0.1) > 0
    L = 0.5
    d = break_even_discount(rc, L)
    assert expected_incremental(rc, rel_lift=L, discount=d) == pytest.approx(0, abs=1e-9)


def test_break_even_impossible_when_discount_exceeds_margin():
    rc = resolve(replace(CFG, discount_pct=0.30, contribution_margin=0.15), CAL)
    assert break_even(rc)["break_even_rel_lift"] == np.inf


def test_sample_size_matches_textbook_formula():
    p0, p1 = 0.10, 0.12
    h = 2 * np.arcsin(np.sqrt(p1)) - 2 * np.arcsin(np.sqrt(p0))
    # Var(2*asin(sqrt(p_hat))) ~= 1/n, so a two-group difference needs n = 2*((z_a + z_b)/h)^2 per arm
    expected = 2 * ((stats.norm.ppf(0.975) + stats.norm.ppf(0.8)) / h) ** 2
    assert sample_size(p0, 0.2) == int(np.ceil(expected))
    # cross-check with the classic unpooled normal-approximation formula (within 1%)
    pbar = (p0 + p1) / 2
    classic = ((stats.norm.ppf(0.975) * np.sqrt(2 * pbar * (1 - pbar))
                + stats.norm.ppf(0.8) * np.sqrt(p0 * (1 - p0) + p1 * (1 - p1))) / (p1 - p0)) ** 2
    assert sample_size(p0, 0.2) == pytest.approx(classic, rel=0.01)


def test_analyze_end_to_end_is_deterministic():
    a = analyze(CFG, CAL, n_boot=50)
    b = analyze(CFG, CAL, n_boot=50)
    assert a["decision"] == b["decision"]
    assert a["is_synthetic"] is True
    assert a["contribution_per_eligible"]["diff"] == b["contribution_per_eligible"]["diff"]


def test_simulator_is_unbiased_against_closed_form():
    """Averaged over many seeds, simulated profit difference converges to the analytical expectation."""
    rc = resolve(CFG, CAL)
    diffs = []
    for s in range(60):
        df = simulate(replace(CFG, seed=1000 + s), CAL)
        g = df.groupby("group").contribution.mean()
        diffs.append(g["treatment"] - g["control"])
    se = np.std(diffs, ddof=1) / np.sqrt(len(diffs))
    assert abs(np.mean(diffs) - expected_incremental(rc)) < 4 * se
