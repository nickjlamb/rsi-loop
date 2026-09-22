"""Canary evaluator. A policy passes iff every canary with an expected label
gets it, and no canary (including the degenerate ones) crashes or returns an
invalid label. Design D.4 said "canary set unchanged"; see design section N
for why that was changed to expected-label semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass
class CanaryReport:
    passed: bool
    n: int
    failures: List[str] = field(default_factory=list)   # expected label not matched
    crashes: List[str] = field(default_factory=list)    # None prediction (error or invalid label)

    def to_dict(self) -> Dict[str, object]:
        return self.__dict__.copy()


def summarise(canaries: Sequence[object], preds: Sequence[Optional[str]]) -> CanaryReport:
    rep = CanaryReport(passed=True, n=len(canaries))
    for c, p in zip(canaries, preds):
        if p is None:
            rep.crashes.append(c.id)
        elif c.expected is not None and p != c.expected:
            rep.failures.append(c.id)
    rep.passed = not rep.failures and not rep.crashes
    return rep
