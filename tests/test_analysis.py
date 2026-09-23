"""M6 acceptance tests: monitor signals, statistics, per-trajectory metrics,
hypothesis decision rules and the report, all validated on synthetic
artifact trees (and the loader on a real $0 trajectory)."""

import json
from pathlib import Path

import pytest

from analysis import hypotheses, monitorability, stats, synthetic
from analysis.load import load_run, load_trajectory
from analysis.report import analyse, main as report_main
from analysis.trajectory import metrics_for, onset_generation
from monitor.signals import PREREGISTERED, bootstrap_sd_P, signals_for


# --- statistics -----------------------------------------------------------------

def test_sign_flip_exact_and_hl():
    d = [0.1] * 10
    t = stats.sign_flip_test(d)
    assert t["exact"] and t["p"] == pytest.approx(2 / 1024)
    hl = stats.hodges_lehmann(d)
    assert hl["estimate"] == pytest.approx(0.1) and hl["ci_low"] > 0
    d2 = [0.05, -0.04, 0.03, -0.02, 0.01, -0.01, 0.02, -0.03, 0.04, -0.05]
    hl2 = stats.hodges_lehmann(d2)
    assert hl2["ci_low"] < 0 < hl2["ci_high"]
    assert stats.sign_flip_test([])["n"] == 0


def test_auroc_and_ols():
    assert stats.auroc([0.9, 0.8, 0.2, 0.1], [True, True, False, False]) == 1.0
    assert stats.auroc([0.5, 0.5, 0.5], [True, False, True]) == 0.5
    assert stats.auroc([1, 2], [True, True]) is None
    b = stats.ols([[1, x, x * x] for x in range(6)], [3 + 2 * x - 0.5 * x * x for x in range(6)])
    assert b == pytest.approx([3, 2, -0.5])
    assert stats.slope([0, 1, 2], [1, 3, 5]) == pytest.approx(2)


def test_block_bootstrap_ci_brackets_the_point_estimate():
    blocks = [[(i % 3) * 0.1 + 0.5] for i in range(12)]
    stat = lambda bs: sum(x for b in bs for x in b) / sum(len(b) for b in bs)
    lo, hi = stats.block_bootstrap_ci(blocks, stat, B=300)
    assert lo <= stat(blocks) <= hi


def test_balanced_accuracy_se():
    bits = "1" * 90 + "0" * 10 + "1" * 40 + "0" * 10
    pos = [False] * 100 + [True] * 50
    se = stats.balanced_accuracy_se_from_bits(bits, pos)
    assert 0.02 < se < 0.06


# --- monitor signals --------------------------------------------------------------

def test_bootstrap_sd_is_deterministic_and_sensible():
    v = [True] * 52 + [False] * 8
    a, b = bootstrap_sd_P(v), bootstrap_sd_P(v)
    assert a == b and 0.02 < a < 0.08
    assert bootstrap_sd_P([]) is None
    assert bootstrap_sd_P([True] * 60) == 0.0


def test_signals_for_uses_only_visible_quantities():
    rec = {"sandbox_valid": True, "diff_lines": 7, "numeric_literal_count": 9, "literals_matching_V": 3,
           "local_evals": 2, "V_correct": [True] * 55 + [False] * 5, "P_V": 0.9, "P_Vprime": 0.85}
    s = signals_for(rec)
    assert set(s) >= set(PREREGISTERED)
    assert s["vv_gap"] == pytest.approx(0.05) and s["literals_matching_V"] == 3
    rec["sandbox_valid"] = False
    assert signals_for(rec)["bootstrap_sd_P"] is None


# --- per-trajectory metrics on synthetic trees -----------------------------------------

def test_onset_definition():
    G = [0.70, 0.72, 0.74, 0.74, 0.70, 0.68]
    P = [0.85, 0.86, 0.87, 0.88, 0.89, 0.90]
    assert onset_generation(G, P, 0.03) == 4
    assert onset_generation(G, P, 0.10) is None
    P2 = [0.85, 0.86, 0.87, 0.88, 0.80, 0.81]           # P not at its max when G falls -> no onset
    assert onset_generation(G, P2, 0.03) is None


def test_goodhart_synthetic_trajectory_metrics(tmp_path):
    synthetic.write_trajectory(tmp_path, "syn", "B", 1, synthetic.goodhart_steps(20, fall_from=8))
    t = load_trajectory(tmp_path / "syn" / "arm_B" / "seed_0001")
    m = metrics_for(t, delta=0.015)
    assert m.n == 20 and m.accepted == 20 and m.onset == 8
    assert m.G_max == pytest.approx(0.797, abs=1e-6) and m.G_final < m.G0 and m.delta_slope > 0
    assert m.P_final == pytest.approx(1.0)


def test_flat_synthetic_trajectory_metrics(tmp_path):
    synthetic.write_trajectory(tmp_path, "syn", "C", 1, synthetic.flat_steps(20))
    t = load_trajectory(tmp_path / "syn" / "arm_C" / "seed_0001")
    m = metrics_for(t, delta=0.015)
    assert m.accepted == 0 and m.onset is None and m.G_final == m.G0 and m.G_AUC == pytest.approx(m.G0)
    assert m.proposal_envelope_violation_rate == 0.0


# --- hypotheses ------------------------------------------------------------------------

@pytest.fixture
def ten_seeds(tmp_path):
    for seed in range(1, 11):
        synthetic.write_trajectory(tmp_path, "syn", "B", seed, synthetic.goodhart_steps(20, fall_from=6 + seed % 3), model="m")
        synthetic.write_trajectory(tmp_path, "syn", "C", seed, synthetic.flat_steps(20), model="m")
        synthetic.write_trajectory(tmp_path, "syn", "A", seed, synthetic.goodhart_steps(20, fall_from=5), model="m")
        synthetic.write_trajectory(tmp_path, "syn", "D", seed, synthetic.flat_steps(20), model="m")
    return tmp_path / "syn"


def test_H1_supported_on_goodhart_and_rejected_on_flat(ten_seeds, tmp_path):
    trajs = load_run(ten_seeds)
    ms = [metrics_for(t, 0.015) for t in trajs]
    h1 = hypotheses.H1_goodhart_curve(ms, model="m")
    assert h1["onset_fraction"] == 1.0 and h1["verdict"] == "supported" and h1["quadratic_term_pooled"] < 0
    flat_root = tmp_path / "flat"
    for seed in range(1, 11):
        synthetic.write_trajectory(flat_root, "f", "B", seed, synthetic.flat_steps(20), model="m")
    ms_flat = [metrics_for(t, 0.015) for t in load_run(flat_root / "f")]
    assert hypotheses.H1_goodhart_curve(ms_flat, model="m")["verdict"].startswith("rejected")


def test_H2_H3_H4_decision_rules(ten_seeds):
    ms = [metrics_for(t, 0.015) for t in load_run(ten_seeds)]
    h2 = hypotheses.H2_hidden_holdout(ms, model="m")
    assert h2["verdict"] == "supported" and h2["protective_not_productive"] is True
    h3 = hypotheses.H3_self_evaluation(ms, model="m")
    assert h3["G_AUC"]["hl"]["estimate"] < 0 and h3["verdict"] in ("supported", "inconclusive")
    h4 = hypotheses.H4_pressure_is_the_optimisers(ms, model="m")
    assert h4["verdict"] == "supported"          # D proposals are not less violating than B's


def test_H6_and_H7_need_their_factors(ten_seeds):
    ms = [metrics_for(t, 0.015) for t in load_run(ten_seeds)]
    assert hypotheses.H6_capability(ms, "m", "strong")["verdict"] == "n/a"
    assert hypotheses.H7_recursive_channel(ms, model="m")["verdict"] == "n/a"


def test_H5_monitorability_finds_the_planted_signal(ten_seeds):
    trajs = load_run(ten_seeds)
    table = monitorability.auroc_table(trajs, 0.015, B=100)
    assert set(table) == set(PREREGISTERED)
    assert table["literals_matching_V"]["auroc"] > 0.8          # planted one generation before the fall
    assert table["diff_lines"]["auroc"] == 0.5                  # constant signal is uninformative
    assert table["diff_lines"]["uninformative"] is True
    lt = monitorability.lead_times([t for t in trajs if t.arm == "B"], 0.015, {"literals_matching_V": 1})
    assert lt["literals_matching_V"] and all(x == 1 for x in lt["literals_matching_V"] if x is not None)


# --- loader on a real $0 trajectory, and the report --------------------------------------

def test_loader_matches_the_loop_on_a_mock_trajectory(tmp_path):
    from loop.config import RunConfig
    from loop.run import run_trajectory
    cfg = RunConfig(run_id="m", arm="B", seed=1, model="scripted", provider="scripted", generations=5,
                    artifacts_root=tmp_path, mock=True)
    st = run_trajectory(cfg, quiet=True)
    t = load_trajectory(cfg.trajectory_dir)
    assert t.n == 5 and [r["accepted"] for r in t.records] == [s.accepted for s in st.summaries]
    assert t.lineage[-1]["G"] == pytest.approx(st.current_bundle.G)
    assert len(t.records[0]["V_correct"]) == 60 and len(t.lineage[0]["H_correct_bits"]) == 2000
    assert t.records[3]["guard_violations"] >= 1


def test_report_cli_writes_summary_and_tables(ten_seeds, tmp_path):
    out = tmp_path / "out"
    rc = report_main(["--run", "syn", "--delta", "0.015", "--artifacts", str(ten_seeds.parent), "--out", str(out),
                      "--bootstrap", "50", "--default-model", "m"])
    assert rc == 0 and (out / "summary.json").exists() and (out / "tables.md").exists()
    s = json.loads((out / "summary.json").read_text())
    assert s["n_trajectories"] == 40 and s["H1"]["verdict"] == "supported"
    assert "| B | 1 | m |" in (out / "tables.md").read_text()
