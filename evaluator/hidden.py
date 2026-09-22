"""Hidden-set scoring: V' (memorisation monitor), H' (hidden gate) and H (G).

Never shown to the optimiser. P_H' is plain accuracy (design D.4, arm C);
G is balanced accuracy on H (design F.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from evaluator.metrics import confusion


@dataclass(frozen=True)
class HiddenScore:
    accuracy: float
    balanced_accuracy: float
    n: int
    frame_errors: int

    def to_dict(self) -> Dict[str, object]:
        return self.__dict__.copy()


def score(truths: Sequence[str], preds: Sequence[Optional[str]]) -> HiddenScore:
    c = confusion(zip(truths, preds))
    return HiddenScore(accuracy=c.accuracy, balanced_accuracy=c.balanced_accuracy, n=c.n,
                       frame_errors=sum(1 for p in preds if p is None))
