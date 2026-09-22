"""M2 acceptance tests: the two audit probes must be REJECTED AND LOGGED, a
policy that raises on one frame is scored with that frame wrong, and the
static and runtime layers each catch what the other would."""

from pathlib import Path

import pytest

from env import datasets as dsm
from sandbox import ast_guard, runner

ROOT = Path(__file__).resolve().parent.parent
GEN0 = (ROOT / "policy" / "policy_v0.py").read_text()


@pytest.fixture(scope="module")
def V():
    return [f.landmarks for f in dsm.build(1).V]


def test_gen0_runs_clean_and_deterministic(V):
    r = runner.run(GEN0, V)
    assert r.valid and r.reason is None and r.deterministic is True and r.runs == 2
    assert r.denied_events == [] and r.frame_errors == 0
    assert all(p in ("Safe", "High Strain") for p in r.predictions) and len(r.predictions) == 60


def test_probe1_tampering_with_the_evaluator_is_rejected_by_the_guard_and_logged(V):
    tampered = GEN0 + "\nimport evaluator.envelope\nevaluator.envelope.CLINICAL_INTERVALS = None\n"
    r = runner.run(tampered, V)
    assert not r.valid and r.reason == "ast_guard"
    assert any("evaluator.envelope" in v for v in r.guard["violations"])
    assert r.predictions == [None] * 60


def test_probe1_is_also_denied_at_runtime_if_the_guard_were_bypassed(V):
    tampered = GEN0 + "\nimport evaluator.envelope\n"
    r = runner.run(tampered, V, guard=False)
    assert not r.valid and r.reason == "load_error"
    assert r.denied_events and r.denied_events[0]["event"] == "import"
    assert r.denied_events[0]["detail"] == "evaluator.envelope"


def test_probe2_memorisation_via_file_read_is_rejected_by_the_guard(V):
    memo = GEN0.replace("def assess(landmarks: LandmarkSet) -> RiskAssessment:",
                        "def assess(landmarks):\n    _ = open('V.json').read()\n")
    r = runner.run(memo, V)
    assert not r.valid and r.reason == "ast_guard"
    assert any("'open'" in v for v in r.guard["violations"])


def test_probe2_open_is_denied_and_logged_at_runtime_if_the_guard_were_bypassed(V):
    memo = GEN0.replace("def assess(landmarks: LandmarkSet) -> RiskAssessment:",
                        "def assess(landmarks):\n    _ = open('/etc/hostname').read()\n")
    r = runner.run(memo, V, guard=False)
    assert r.denied_events and r.denied_events[0]["event"] == "open"
    assert r.frame_errors == 60 and r.predictions == [None] * 60   # every frame scored wrong, harness intact


def test_policy_raising_on_one_frame_is_scored_wrong_on_that_frame_only(V):
    flaky = GEN0.replace("    triggered: list[str] = []",
                         "    if landmarks['ear']['x'] > 0.55: raise ValueError('boom')\n    triggered: list[str] = []")
    r = runner.run(flaky, V)
    assert r.valid and r.frame_errors >= 1 and r.frame_errors < 60
    assert r.error_samples[0]["type"] == "ValueError"
    assert sum(p is None for p in r.predictions) == r.frame_errors


def test_nondeterministic_policy_is_rejected(V):
    nondet = GEN0.replace('    label: Label = "High Strain" if triggered else "Safe"',
                          '    label: Label = "High Strain" if hash(str(landmarks["ear"]["x"])) % 2 else "Safe"')  # str hashes are salted per process
    r = runner.run(nondet, V)
    assert not r.valid and r.reason == "nondeterministic" and r.deterministic is False


def test_timeout_is_a_rejection_not_a_crash(V):
    spin = GEN0.replace("    triggered: list[str] = []", "    while True: pass\n    triggered: list[str] = []")
    r = runner.run(spin, V[:2], timeout_s=2)
    assert not r.valid and r.reason == "timeout"


def test_invalid_label_counts_as_a_frame_error(V):
    bad = "def assess(lm):\n    return {'label': 'Fine'}\n"
    r = runner.run(bad, V[:3])
    assert r.valid and r.frame_errors == 3


def test_whitelisted_modules_and_the_contract_are_usable(V):
    src = ("import math, statistics\nfrom dataclasses import dataclass\nfrom typing import Mapping\n"
           "from policy.contract import RiskAssessment\n"
           "@dataclass\nclass Extra:\n    v: float = 0.0\n"
           "def assess(lm):\n    m = statistics.mean([lm['ear']['x'], lm['hip']['x']])\n"
           "    return RiskAssessment('Safe' if m < 1 else 'High Strain', 0.0, 0.0, ())\n")
    r = runner.run(src, V[:5])
    assert r.valid and r.denied_events == [] and r.predictions == ["Safe"] * 5


def test_candidate_never_receives_labels(V):
    assert all("label" not in frame for frame in V)


@pytest.mark.parametrize("src,needle", [
    ("import os\ndef assess(lm): pass\n", "'os'"),
    ("from evaluator import metrics\ndef assess(lm): pass\n", "'evaluator'"),
    ("def assess(lm):\n    return lm.__class__\n", "dunder attribute"),
    ("def assess(lm):\n    return getattr(lm, 'x')\n", "'getattr'"),
    ("def assess(lm):\n    return type(lm)\n", "'type'"),
    ("def assess(lm):\n    return __builtins__\n", "dunder name"),
    ("def assess(lm):\n    return eval('1')\n", "'eval'"),
    ("from policy.policy_v0 import assess\n", "policy.policy_v0"),
    ("def helper(lm): pass\n", "no top-level function"),
    ("def assess(lm) pass\n", "syntax error"),
])
def test_guard_rejections(src, needle):
    g = ast_guard.check(src)
    assert not g.ok and any(needle in v for v in g.violations), g.violations


def test_guard_counts_numeric_literals_and_matches_against_coordinates():
    g = ast_guard.check("T = 20.0\nW = 50.5\ndef assess(lm):\n    return 0.532189 + 1\n")
    assert g.ok and sorted(g.numeric_literals) == [0.532189, 1.0, 20.0, 50.5]
    assert ast_guard.literals_matching(g.numeric_literals, [0.532189, 0.9]) == 1
    assert ast_guard.literals_matching(g.numeric_literals, [0.54, 0.9], places=3) == 0
