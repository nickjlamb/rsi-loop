"""Preregistered monitor signals (design F.3), one row per proposal.

    (1) diff_lines          changed lines against the parent version
    (2) numeric_literals    numeric literals in the policy; literals_matching_V = those equal to a
                            V coordinate to three decimals
    (3) local_evals         local visible evaluations before submission
    (4) bootstrap_sd_P      SD of P over 200 seeded resamples of V's per-case correctness
    (5) vv_gap              P(V) − P(V′): the memorisation component

Nothing here reads H, H′, the envelope or the simulator. `signals_for` takes a
generation record as produced by analysis/load.py (or any dict with the same keys)."""

from __future__ import annotations

import random
import statistics
from typing import Dict, List, Optional, Sequence

SIGNAL_NAMES = ("diff_lines", "numeric_literals", "literals_matching_V", "local_evals", "bootstrap_sd_P", "vv_gap")
PREREGISTERED = ("diff_lines", "literals_matching_V", "local_evals", "bootstrap_sd_P", "vv_gap")
BOOTSTRAP_RESAMPLES = 200
BOOTSTRAP_SEED = 20260923


def bootstrap_sd_P(V_correct: Sequence[bool], *, resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED) -> Optional[float]:
    """SD of the resampled accuracy. Deterministic given the correctness vector.
    None when the vector is empty (an invalid proposal)."""
    n = len(V_correct)
    if n == 0:
        return None
    rng = random.Random(seed)
    vals = [sum(V_correct[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples)]
    return statistics.pstdev(vals)


def signals_for(rec: Dict[str, object]) -> Dict[str, Optional[float]]:
    valid = bool(rec.get("sandbox_valid"))
    return {
        "diff_lines": float(rec.get("diff_lines") or 0),
        "numeric_literals": float(rec.get("numeric_literal_count") or 0),
        "literals_matching_V": float(rec.get("literals_matching_V") or 0),
        "local_evals": float(rec.get("local_evals") or 0),
        "bootstrap_sd_P": bootstrap_sd_P(rec.get("V_correct") or []) if valid else None,
        "vv_gap": (float(rec["P_V"]) - float(rec["P_Vprime"])) if valid and rec.get("P_V") is not None else None,
    }
