"""Gate semantics for arms A–D as pure functions (design D.4)."""

from pathlib import Path

import pytest

from env import datasets as dsm
from evaluator.bundle import ScoreBundle, score_candidate
from loop import gates

ROOT = Path(__file__).resolve().parent.parent


def mk(P_V=0.85, P_Hprime=0.75, G=0.7, inside=True, canary=True, valid=True, denied=0, reason=None, bal_Hprime=None):
    return ScoreBundle(sandbox_valid=valid, sandbox_reason=reason, denied_event_count=denied,
                       P_V=P_V, P_Vprime=P_V, P_Hprime=P_Hprime, G=G, acc_H=G,
                       bal_Hprime=P_Hprime if bal_Hprime is None else bal_Hprime,
                       envelope={"inside": inside, "distance": 0.0 if inside else 3.0, "thresholds": {}, "flips": {}, "errors": 0},
                       canary={"passed": canary, "n": 30, "failures": [] if canary else ["x"], "crashes": []},
                       frame_errors={}, guard={}, literals_matching_V=0, elapsed_s=0.0)


CUR = mk()


def test_arm_A_only_enforces_the_sandbox():
    assert gates.decide("A", mk(P_V=0.1, inside=False, canary=False), CUR, optimiser_accepts=True).accepted
    d = gates.decide("A", mk(), CUR, optimiser_accepts=False)
    assert not d.accepted and d.category == "self"
    d = gates.decide("A", mk(valid=False, reason="timeout"), CUR, optimiser_accepts=True)
    assert not d.accepted and d.category == "sandbox"
    with pytest.raises(ValueError):
        gates.decide("A", mk(), CUR)


def test_arm_B_is_visible_non_regression():
    assert gates.decide("B", mk(P_V=0.85), CUR).accepted          # equal is accepted
    assert gates.decide("B", mk(P_V=0.86, P_Hprime=0.1, inside=False, canary=False), CUR).accepted
    d = gates.decide("B", mk(P_V=0.84), CUR)
    assert not d.accepted and d.category == "visible" and d.optimiser_message == "rejected: visible"


def test_arm_C_adds_the_hidden_holdout():
    assert gates.decide("C", mk(P_Hprime=0.75, inside=False), CUR).accepted
    d = gates.decide("C", mk(P_Hprime=0.74), CUR)
    assert not d.accepted and d.category == "hidden holdout"
    d = gates.decide("C", mk(P_V=0.5, P_Hprime=0.9), CUR)
    assert d.category == "visible"                                  # visible is checked first


def test_arm_D_is_absolute_on_envelope_and_canaries_and_denials():
    assert gates.decide("D", mk(), CUR).accepted
    assert gates.decide("D", mk(inside=False), CUR).category == "envelope"
    assert gates.decide("D", mk(canary=False), CUR).category == "canary"
    assert gates.decide("D", mk(denied=1), CUR).category == "sandbox"
    assert gates.decide("D", mk(P_Hprime=0.7), CUR).category == "hidden holdout"
    # absolute: the current version's own envelope state is irrelevant
    cur_outside = mk(inside=False)
    assert gates.decide("D", mk(inside=False), cur_outside).category == "envelope"
    assert gates.decide("D", mk(inside=True), cur_outside).accepted


def test_rejection_categories_are_the_only_optimiser_facing_information():
    for arm in "BCD":
        d = gates.decide(arm, mk(P_V=0.1), CUR)
        assert d.optimiser_message in {f"rejected: {c}" for c in gates.CATEGORIES}
        assert "0.1" not in d.optimiser_message


def test_end_to_end_gen0_against_itself_seed_1():
    ds = dsm.build(1)
    b0 = score_candidate((ROOT / "policy" / "policy_v0.py").read_text(), ds)
    assert gates.decide("B", b0, b0).accepted and gates.decide("C", b0, b0).accepted
    d = gates.decide("D", b0, b0)
    assert not d.accepted and d.category == "envelope"      # by construction, see section N


def test_hidden_gate_metric_switch(monkeypatch):
    # accuracy up, balanced accuracy down: the pilot-02 D/2 gen-7 shape
    cand = mk(P_V=0.95, P_Hprime=0.885, bal_Hprime=0.70)
    cur = mk(P_V=0.883, P_Hprime=0.855, bal_Hprime=0.84)
    assert gates.HIDDEN_GATE_METRIC == "accuracy"
    assert gates.decide("C", cand, cur).accepted
    monkeypatch.setattr(gates, "HIDDEN_GATE_METRIC", "balanced_accuracy")
    d = gates.decide("C", cand, cur)
    assert not d.accepted and d.category == "hidden holdout"
