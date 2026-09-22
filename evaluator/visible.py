"""Visible evaluator — the descendant of legacy/test_engine.py.

Runs a policy on the PUBLIC view of V through the sandbox and returns P plus a
report at the arm's detail level. This is the only evaluator whose output the
optimiser ever sees, so it takes public frames (id, landmarks, label) and
nothing else, and its report contains nothing derived from hidden sets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Sequence

from evaluator.metrics import confusion
from sandbox import runner

Detail = Literal["aggregate", "per-case"]


@dataclass
class VisibleReport:
    P: float
    n: int
    correct: int
    confusion: Dict[str, int]
    sandbox_valid: bool
    sandbox_reason: Optional[str]
    frame_errors: int
    per_case: List[Dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return self.__dict__.copy()


def score(truths: Sequence[str], preds: Sequence[Optional[str]]) -> float:
    """P: plain accuracy; a failed frame (None) counts as wrong."""
    return confusion(zip(truths, preds)).accuracy


def evaluate(source: str, public_frames: Sequence[Dict[str, object]], detail: Detail = "per-case") -> VisibleReport:
    for f in public_frames:
        assert set(f) == {"id", "landmarks", "label"}, "visible evaluator accepts public frames only"
    res = runner.run(source, [f["landmarks"] for f in public_frames])
    truths = [str(f["label"]) for f in public_frames]
    preds = res.predictions
    c = confusion(zip(truths, preds))
    rep = VisibleReport(P=c.accuracy, n=c.n, correct=c.tp + c.tn,
                        confusion={"tp": c.tp, "tn": c.tn, "fp": c.fp, "fn": c.fn},
                        sandbox_valid=res.valid, sandbox_reason=res.reason, frame_errors=res.frame_errors)
    if detail == "per-case":
        for f, p, m in zip(public_frames, preds, res.metrics or [[None, None]] * len(preds)):
            rep.per_case.append({"id": f["id"], "expected": f["label"], "predicted": p, "correct": p == f["label"],
                                 "forward_head_metric": m[0], "wrist_deviation_metric": m[1]})
    return rep
