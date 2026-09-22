"""Metric definitions. Every quantity in the preregistration that is computed
from labels is defined here and pinned by tests/test_metrics.py, including
denominators.

Conventions: the positive class is "High Strain". Balanced accuracy is the
mean of recall on each class; a class with zero support contributes 0.5 so
that a degenerate set does not raise (this can only happen in tests)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple

POSITIVE = "High Strain"
NEGATIVE = "Safe"


@dataclass(frozen=True)
class Confusion:
    tp: int
    tn: int
    fp: int
    fn: int

    @property
    def n(self) -> int:
        return self.tp + self.tn + self.fp + self.fn

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.n if self.n else 0.0

    @property
    def recall(self) -> float:            # true-positive rate
        d = self.tp + self.fn
        return self.tp / d if d else 0.5

    @property
    def specificity(self) -> float:       # true-negative rate
        d = self.tn + self.fp
        return self.tn / d if d else 0.5

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def balanced_accuracy(self) -> float:
        return 0.5 * (self.recall + self.specificity)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def prevalence(self) -> float:
        return (self.tp + self.fn) / self.n if self.n else 0.0


def confusion(pairs: Iterable[Tuple[str, str]]) -> Confusion:
    """pairs of (true_label, predicted_label)."""
    tp = tn = fp = fn = 0
    for truth, pred in pairs:
        if truth == POSITIVE:
            if pred == POSITIVE:
                tp += 1
            else:
                fn += 1
        else:
            if pred == POSITIVE:
                fp += 1
            else:
                tn += 1
    return Confusion(tp, tn, fp, fn)


def accuracy(truths: Sequence[str], preds: Sequence[str]) -> float:
    """P in the preregistration: plain accuracy (used on V and V')."""
    return confusion(zip(truths, preds)).accuracy


def balanced_accuracy(truths: Sequence[str], preds: Sequence[str]) -> float:
    """G in the preregistration: balanced accuracy (used on H)."""
    return confusion(zip(truths, preds)).balanced_accuracy
