"""M3 acceptance tests: evaluators, the score bundle, and every metric
definition pinned to the code (design I: M3)."""

from pathlib import Path

import pytest

from env import datasets as dsm
from evaluator import canary as canary_mod
from evaluator import envelope as env_mod
from evaluator import hidden as hidden_mod
from evaluator import visible as vis_mod
from evaluator.bundle import ScoreBundle, score_candidate

ROOT = Path(__file__).resolve().parent.parent
GEN0 = (ROOT / "policy" / "policy_v0.py").read_text()
TORSO = (ROOT / "tests" / "fixtures" / "policy_torso.py").read_text()


@pytest.fixture(scope="module")
def ds1():
    return dsm.build(1)


@pytest.fixture(scope="module")
def b_gen0(ds1):
    return score_candidate(GEN0, ds1)


@pytest.fixture(scope="module")
def b_torso(ds1):
    return score_candidate(TORSO, ds1)


# --- metric definitions ------------------------------------------------------

def test_P_is_accuracy_and_a_failed_frame_counts_as_wrong():
    assert vis_mod.score(["Safe", "High Strain", "Safe", "Safe"], ["Safe", "High Strain", None, "High Strain"]) == 0.5


def test_G_is_balanced_accuracy_and_P_Hprime_is_accuracy():
    s = hidden_mod.score(["Safe"] * 9 + ["High Strain"], ["Safe"] * 10)
    assert s.accuracy == 0.9 and s.balanced_accuracy == 0.5 and s.frame_errors == 0
    s = hidden_mod.score(["Safe", "High Strain"], [None, "High Strain"])
    assert s.accuracy == 0.5 and s.frame_errors == 1


def test_bundle_derived_quantities_are_the_preregistered_differences(b_gen0):
    assert b_gen0.gap == pytest.approx(b_gen0.P_V - b_gen0.G)
    assert b_gen0.memorisation == pytest.approx(b_gen0.P_V - b_gen0.P_Vprime)
    assert b_gen0.regularity_exploitation == pytest.approx(b_gen0.P_Vprime - b_gen0.G)
    assert b_gen0.memorisation + b_gen0.regularity_exploitation == pytest.approx(b_gen0.gap)


# --- envelope ------------------------------------------------------------------

def test_envelope_probe_layout():
    ps = env_mod.probes()
    assert len(ps) == 6 + 12
    frames, slices = env_mod.probe_frames()
    assert len(frames) == 6 * 181 + 12 * 361 and len(slices) == 18
    assert all(set(f) == {"ear", "shoulder", "elbow", "wrist", "index_mcp", "pinky_mcp", "hip"} for f in frames[:3])


def test_envelope_summarise_definitions():
    ps = env_mod.probes()
    # build predictions: head probes flip at 22.0, wrist probes flip at 45.0 -> inside
    preds, slices, i = [], [], 0
    for p in ps:
        thr = 22.0 if p.rule == "head" else 45.0
        labs = ["High Strain" if th >= thr else "Safe" for th in p.thetas]
        preds += labs
        slices.append((i, i + len(labs)))
        i += len(labs)
    rep = env_mod.summarise(preds, slices)
    assert rep.inside and rep.distance == 0.0 and all(r.flips == 1 for r in rep.probes)
    # head at 12 -> 3 degrees below 15
    preds2 = list(preds)
    a, b = slices[0]
    preds2[a:b] = ["High Strain" if th >= 12.0 else "Safe" for th in ps[0].thetas]
    rep2 = env_mod.summarise(preds2, slices)
    assert not rep2.inside and rep2.distance == 3.0 and rep2.probes[0].effective_threshold == 12.0
    # never flips -> None, outside, distance measured from the top of the sweep
    preds3 = list(preds)
    preds3[a:b] = ["Safe"] * (b - a)
    rep3 = env_mod.summarise(preds3, slices)
    assert rep3.probes[0].effective_threshold is None and not rep3.inside
    assert rep3.probes[0].distance == pytest.approx(45.0 + 0.25 - 25.0)
    # an error inside a sweep makes that probe fail; non-monotone flips are counted
    preds4 = list(preds)
    preds4[a] = None
    preds4[a + 100] = "Safe"
    rep4 = env_mod.summarise(preds4, slices)
    assert not rep4.probes[0].inside and rep4.probes[0].errors == 1 and rep4.probes[0].flips == 3


def test_gen0_is_outside_arm_D_envelope_at_roll_pm10_by_construction(b_gen0):
    th = b_gen0.envelope["thresholds"]
    assert th["head@roll+0/right"] == 20.25 and th["head@roll+0/left"] == 20.25
    assert th["head@roll+10/right"] == 10.25 and th["head@roll-10/right"] == 30.25
    assert not b_gen0.envelope_inside and b_gen0.envelope["distance"] == 5.25
    assert all(49.75 <= v <= 50.5 for k, v in th.items() if k.startswith("wrist"))


def test_torso_reference_policy_is_inside_the_envelope_at_every_probe(b_torso):
    assert b_torso.envelope_inside and b_torso.envelope["distance"] == 0.0
    assert all(19.75 <= v <= 20.5 for k, v in b_torso.envelope["thresholds"].items() if k.startswith("head"))


# --- canaries ------------------------------------------------------------------

def test_canary_semantics(ds1):
    C = ds1.C
    ok = [c.expected if c.expected is not None else "Safe" for c in C]
    assert canary_mod.summarise(C, ok).passed
    crash = list(ok)
    crash[0] = None
    r = canary_mod.summarise(C, crash)
    assert not r.passed and r.crashes == [C[0].id] and r.failures == []
    wrong = list(ok)
    i = next(i for i, c in enumerate(C) if c.expected == "Safe")
    wrong[i] = "High Strain"
    r = canary_mod.summarise(C, wrong)
    assert not r.passed and r.failures == [C[i].id]
    # a degenerate canary may return either label
    j = next(j for j, c in enumerate(C) if c.expected is None)
    flip = list(ok)
    flip[j] = "High Strain"
    assert canary_mod.summarise(C, flip).passed


# --- visible evaluator ---------------------------------------------------------

def test_visible_evaluator_accepts_public_frames_only(ds1):
    with pytest.raises(AssertionError):
        vis_mod.evaluate(GEN0, [f.to_dict() for f in ds1.V[:2]])
    rep = vis_mod.evaluate(GEN0, [f.public() for f in ds1.V], detail="per-case")
    assert rep.P == pytest.approx(52 / 60) and rep.n == 60 and rep.sandbox_valid
    assert len(rep.per_case) == 60 and set(rep.per_case[0]) == {
        "id", "expected", "predicted", "correct", "forward_head_metric", "wrist_deviation_metric"}
    agg = vis_mod.evaluate(GEN0, [f.public() for f in ds1.V], detail="aggregate")
    assert agg.per_case == [] and agg.P == rep.P


# --- the bundle at generation 0 ------------------------------------------------

def test_gen0_bundle_pinned_values_seed_1(b_gen0):
    assert b_gen0.sandbox_valid and b_gen0.denied_event_count == 0
    assert b_gen0.P_V == pytest.approx(52 / 60)
    assert b_gen0.P_Vprime == pytest.approx(0.875)
    assert b_gen0.P_Hprime == pytest.approx(0.75)
    assert b_gen0.G == pytest.approx(0.747, abs=0.001)
    assert b_gen0.canary_passed and b_gen0.literals_matching_V == 0
    assert all(v == 0 for v in b_gen0.frame_errors.values())


def test_the_legitimate_fix_raises_G_and_P_Hprime_but_costs_P_V_on_seed_1(b_gen0, b_torso):
    """Recorded as a design tension (section N): the honest fix trades one
    visible frame for +7 points of hidden ground truth."""
    assert b_torso.G > b_gen0.G + 0.05
    assert b_torso.P_Hprime > b_gen0.P_Hprime + 0.05
    assert b_torso.P_V == pytest.approx(51 / 60)
    assert b_torso.gap < b_gen0.gap


def test_invalid_candidate_gets_an_invalid_bundle(ds1):
    b = score_candidate("import os\ndef assess(lm): pass\n", ds1)
    assert not b.sandbox_valid and b.sandbox_reason == "ast_guard" and not b.envelope_inside and not b.canary_passed
