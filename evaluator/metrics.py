"""Metric definitions. Every quantity in the preregistration that is computed
from labels is defined here and pinned by tests/test_metrics.py, including
denominators.

Conventions: the positive class is "High Strain". A prediction that is not a
valid label (None: the policy crashed on that frame, or returned garbage) is an
ERROR: it is wrong for accuracy and it sits in the denominator of its true
class's rate, but it is neither a false positive nor a false negative.
Balanced accuracy is the mean of recall and specificity; a class with zero
support contributes 0.5 so a degenerate set does not raise."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

POSITIVE = "High Strain"
NEGATIVE = "Safe"
LABELS = (POSITIVE, NEGATIVE)


@dataclass(frozen=True)
class Confusion:
    tp: int
    tn: int
    fp: int
    fn: int
    err_pos: int = 0     # positives with an invalid prediction
    err_neg: int = 0     # negatives with an invalid prediction

    @property
    def n(self) -> int:
        return self.tp + self.tn + self.fp + self.fn + self.err_pos + self.err_neg

    @property
    def errors(self) -> int:
        return self.err_pos + self.err_neg

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.n if self.n else 0.0

    @property
    def recall(self) -> float:            # true-positive rate
        d = self.tp + self.fn + self.err_pos
        return self.tp / d if d else 0.5

    @property
    def specificity(self) -> float:       # true-negative rate
        d = self.tn + self.fp + self.err_neg
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
        return (self.tp + self.fn + self.err_pos) / self.n if self.n else 0.0


def confusion(pairs: Iterable[Tuple[str, Optional[str]]]) -> Confusion:
    """pairs of (true_label, predicted_label_or_None)."""
    tp = tn = fp = fn = ep = en = 0
    for truth, pred in pairs:
        if pred not in LABELS:
            if truth == POSITIVE:
                ep += 1
            else:
                en += 1
        elif truth == POSITIVE:
            if pred == POSITIVE:
                tp += 1
            else:
                fn += 1
        else:
            if pred == POSITIVE:
                fp += 1
            else:
                tn += 1
    return Confusion(tp, tn, fp, fn, ep, en)


def accuracy(truths: Sequence[str], preds: Sequence[Optional[str]]) -> float:
    """P in the preregistration: plain accuracy (used on V, V' and H')."""
    return confusion(zip(truths, preds)).accuracy


def balanced_accuracy(truths: Sequence[str], preds: Sequence[Optional[str]]) -> float:
    """G in the preregistration: balanced accuracy (used on H)."""
    return confusion(zip(truths, preds)).balanced_accuracy
