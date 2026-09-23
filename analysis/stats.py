"""Statistical primitives (design F.4), pure standard library.

    sign_flip_test(diffs)         exact (n ≤ 14) or Monte-Carlo two-sided test of mean difference = 0
    hodges_lehmann(diffs)         HL estimate with an exact signed-rank 95% CI (Walsh averages)
    auroc(scores, labels)         Mann–Whitney AUROC with tie handling
    block_bootstrap_ci(...)       percentile CI over trajectories
    ols(xs_rows, y)               ordinary least squares by normal equations (tiny designs only)
    binomial_se(p, n)             standard error of a proportion
"""

from __future__ import annotations

import itertools
import math
import random
import statistics
from typing import Callable, Dict, List, Optional, Sequence, Tuple

EXACT_MAX_N = 14


def sign_flip_test(diffs: Sequence[float], *, n_mc: int = 20000, seed: int = 1) -> Dict[str, float]:
    d = [x for x in diffs if x is not None]
    n = len(d)
    if n == 0:
        return {"n": 0, "mean": float("nan"), "p": float("nan"), "exact": True}
    obs = abs(sum(d))
    if n <= EXACT_MAX_N:
        count = total = 0
        for signs in itertools.product((1, -1), repeat=n):
            total += 1
            if abs(sum(s * x for s, x in zip(signs, d))) >= obs - 1e-12:
                count += 1
        return {"n": n, "mean": sum(d) / n, "p": count / total, "exact": True}
    rng = random.Random(seed)
    count = 0
    for _ in range(n_mc):
        if abs(sum(x if rng.random() < 0.5 else -x for x in d)) >= obs - 1e-12:
            count += 1
    return {"n": n, "mean": sum(d) / n, "p": (count + 1) / (n_mc + 1), "exact": False}


def _signed_rank_lower_k(n: int, alpha: float = 0.05) -> int:
    """Largest k with P(T+ <= k) <= alpha/2 under the null, by exact enumeration."""
    counts: Dict[int, int] = {}
    for signs in itertools.product((0, 1), repeat=n):
        t = sum((i + 1) for i, s in enumerate(signs) if s)
        counts[t] = counts.get(t, 0) + 1
    total = 2 ** n
    cum = 0
    k = -1
    for t in sorted(counts):
        if (cum + counts[t]) / total <= alpha / 2:
            cum += counts[t]
            k = t
        else:
            break
    return k


def hodges_lehmann(diffs: Sequence[float], alpha: float = 0.05) -> Dict[str, Optional[float]]:
    d = [x for x in diffs if x is not None]
    n = len(d)
    if n == 0:
        return {"n": 0, "estimate": None, "ci_low": None, "ci_high": None}
    walsh = sorted((d[i] + d[j]) / 2 for i in range(n) for j in range(i, n))
    est = statistics.median(walsh)
    if n > EXACT_MAX_N:
        return {"n": n, "estimate": est, "ci_low": None, "ci_high": None}
    k = _signed_rank_lower_k(n, alpha)
    m = len(walsh)
    if k < 0:                           # n too small for a CI at this alpha (n < 6)
        return {"n": n, "estimate": est, "ci_low": walsh[0], "ci_high": walsh[-1], "ci_note": "n too small; full range"}
    return {"n": n, "estimate": est, "ci_low": walsh[k], "ci_high": walsh[m - 1 - k]}


def auroc(scores: Sequence[Optional[float]], labels: Sequence[bool]) -> Optional[float]:
    pairs = [(s, l) for s, l in zip(scores, labels) if s is not None]
    pos = [s for s, l in pairs if l]
    neg = [s for s, l in pairs if not l]
    if not pos or not neg:
        return None
    total = 0.0
    for p in pos:
        for q in neg:
            total += 1.0 if p > q else (0.5 if p == q else 0.0)
    return total / (len(pos) * len(neg))


def block_bootstrap_ci(blocks: Sequence[object], statistic: Callable[[Sequence[object]], Optional[float]], *,
                       B: int = 1000, alpha: float = 0.05, seed: int = 7) -> Tuple[Optional[float], Optional[float]]:
    """Percentile CI of `statistic` under resampling of whole blocks (trajectories)."""
    rng = random.Random(seed)
    n = len(blocks)
    if n == 0:
        return None, None
    vals: List[float] = []
    for _ in range(B):
        sample = [blocks[rng.randrange(n)] for _ in range(n)]
        v = statistic(sample)
        if v is not None:
            vals.append(v)
    if not vals:
        return None, None
    vals.sort()
    lo = vals[int(math.floor(alpha / 2 * (len(vals) - 1)))]
    hi = vals[int(math.ceil((1 - alpha / 2) * (len(vals) - 1)))]
    return lo, hi


def ols(rows: Sequence[Sequence[float]], y: Sequence[float]) -> Optional[List[float]]:
    """Solve (X'X) b = X'y by Gaussian elimination. rows are design-matrix rows."""
    if not rows:
        return None
    k = len(rows[0])
    xtx = [[sum(r[i] * r[j] for r in rows) for j in range(k)] for i in range(k)]
    xty = [sum(r[i] * yi for r, yi in zip(rows, y)) for i in range(k)]
    a = [xtx[i][:] + [xty[i]] for i in range(k)]
    for c in range(k):
        piv = max(range(c, k), key=lambda r: abs(a[r][c]))
        if abs(a[piv][c]) < 1e-12:
            return None
        a[c], a[piv] = a[piv], a[c]
        for r in range(k):
            if r != c:
                f = a[r][c] / a[c][c]
                a[r] = [x - f * y_ for x, y_ in zip(a[r], a[c])]
    return [a[i][k] / a[i][i] for i in range(k)]


def slope(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    pts = [(x, y) for x, y in zip(xs, ys) if y is not None]
    if len(pts) < 2:
        return None
    b = ols([[1.0, x] for x, _ in pts], [y for _, y in pts])
    return None if b is None else b[1]


def binomial_se(p: float, n: int) -> float:
    return math.sqrt(max(p * (1 - p), 0.0) / n) if n else float("nan")


def balanced_accuracy_se_from_bits(bits: str, positives: Sequence[bool]) -> Optional[float]:
    """SE of balanced accuracy from per-frame correctness and class membership,
    treating the two class recalls as independent binomials."""
    if not bits or len(bits) != len(positives):
        return None
    pos = [b == "1" for b, p in zip(bits, positives) if p]
    neg = [b == "1" for b, p in zip(bits, positives) if not p]
    if not pos or not neg:
        return None
    rp, rn = sum(pos) / len(pos), sum(neg) / len(neg)
    return 0.5 * math.sqrt(binomial_se(rp, len(pos)) ** 2 + binomial_se(rn, len(neg)) ** 2)
