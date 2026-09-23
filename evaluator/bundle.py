"""Score one candidate on everything, in one sandbox run.

    bundle = score_candidate(source, datasets)

Every proposal — accepted or rejected — gets a full bundle (design D.2). The
gates in loop/gates.py are pure functions of two bundles (candidate, current).
All frames go through the sandbox in a single concatenated call so there is
one determinism check and one pair of interpreters per candidate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from env.datasets import Datasets
from evaluator import canary as canary_mod
from evaluator import envelope as envelope_mod
from evaluator import hidden as hidden_mod
from evaluator.visible import score as visible_score
from sandbox import runner
from sandbox.ast_guard import literals_matching


@dataclass
class ScoreBundle:
    sandbox_valid: bool
    sandbox_reason: Optional[str]
    denied_event_count: int
    P_V: float                      # accuracy on V (P)
    P_Vprime: float                 # accuracy on V'
    P_Hprime: float                 # accuracy on H' (hidden gate quantity)
    G: float                        # balanced accuracy on H
    acc_H: float
    envelope: Dict[str, object]     # EnvelopeReport.to_dict()
    canary: Dict[str, object]       # CanaryReport.to_dict()
    frame_errors: Dict[str, int]
    guard: Dict[str, object]
    literals_matching_V: int
    elapsed_s: float = 0.0
    denied_events: List[Dict[str, object]] = field(default_factory=list)

    # --- derived quantities (design F.1, F.2) -------------------------------
    @property
    def gap(self) -> float:                 # Δ = P − G
        return self.P_V - self.G

    @property
    def memorisation(self) -> float:        # P(V) − P(V')
        return self.P_V - self.P_Vprime

    @property
    def regularity_exploitation(self) -> float:   # P(V') − G(H)
        return self.P_Vprime - self.G

    @property
    def envelope_inside(self) -> bool:
        return bool(self.envelope.get("inside", False))

    @property
    def canary_passed(self) -> bool:
        return bool(self.canary.get("passed", False))

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        d.update({"gap": self.gap, "memorisation": self.memorisation,
                  "regularity_exploitation": self.regularity_exploitation})
        return d


def invalid_bundle(res: runner.SandboxResult) -> ScoreBundle:
    return ScoreBundle(sandbox_valid=False, sandbox_reason=res.reason, denied_event_count=len(res.denied_events),
                       P_V=0.0, P_Vprime=0.0, P_Hprime=0.0, G=0.0, acc_H=0.0,
                       envelope={"inside": False, "distance": float("inf"), "thresholds": {}, "flips": {}, "errors": 0},
                       canary={"passed": False, "n": 0, "failures": [], "crashes": []},
                       frame_errors={}, guard=res.guard, literals_matching_V=0, elapsed_s=res.elapsed_s,
                       denied_events=list(res.denied_events))


def score_candidate(source: str, ds: Datasets, *, timeout_s: float = runner.DEFAULT_TIMEOUT_S) -> ScoreBundle:
    frames: List[Dict[str, Dict[str, float]]] = []
    spans: Dict[str, tuple] = {}
    for name, fs in ds.sets().items():
        a = len(frames)
        frames.extend(f.landmarks for f in fs)
        spans[name] = (a, len(frames))
    a = len(frames)
    frames.extend(c.landmarks for c in ds.C)
    spans["C"] = (a, len(frames))
    env_frames, env_slices = envelope_mod.probe_frames()
    a = len(frames)
    frames.extend(env_frames)
    spans["E"] = (a, len(frames))

    res = runner.run(source, frames, timeout_s=timeout_s)
    if not res.valid:
        return invalid_bundle(res)

    def preds(name: str):
        s, e = spans[name]
        return res.predictions[s:e]

    def truths(name: str):
        return [f.label for f in ds.sets()[name]]

    v = visible_score(truths("V"), preds("V"))
    vp = hidden_mod.score(truths("V_prime"), preds("V_prime"))
    hp = hidden_mod.score(truths("H_prime"), preds("H_prime"))
    h = hidden_mod.score(truths("H"), preds("H"))
    can = canary_mod.summarise(ds.C, preds("C"))
    s, e = spans["E"]
    env = envelope_mod.summarise(res.predictions[s:e], env_slices)

    coords = [c for f in ds.V for lm in f.landmarks.values() for c in (lm["x"], lm["y"])]
    return ScoreBundle(
        sandbox_valid=True, sandbox_reason=None, denied_event_count=len(res.denied_events),
        P_V=v, P_Vprime=vp.accuracy, P_Hprime=hp.accuracy, G=h.balanced_accuracy, acc_H=h.accuracy,
        envelope=env.to_dict(), canary=can.to_dict(),
        frame_errors={n: sum(1 for p in preds(n) if p is None) for n in list(ds.sets()) + ["C", "E"]},
        guard=res.guard, literals_matching_V=literals_matching(
            [float(x) for x in _guard_literals(source)], coords),
        elapsed_s=res.elapsed_s, denied_events=list(res.denied_events))


def _guard_literals(source: str) -> List[float]:
    from sandbox.ast_guard import check
    return check(source).numeric_literals
