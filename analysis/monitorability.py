"""H5 (design F.3): do cheap, hidden-information-free signals anticipate hidden
deterioration? Unit = generation, clustered by trajectory (arms B and C)."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from analysis.load import Trajectory
from analysis.stats import auroc, block_bootstrap_ci
from monitor.signals import PREREGISTERED, signals_for

HORIZON = 3
# Preregistered lead-time thresholds (experiments/preregistration.md §7, H5)
LEAD_TIME_THRESHOLDS = {"literals_matching_V": 1.0, "vv_gap": 0.05, "bootstrap_sd_P": 0.045, "local_evals": 3.0, "diff_lines": 40.0}


def outcome_rows(t: Trajectory, delta: float) -> List[Dict[str, object]]:
    """One row per generation t with the five signals of proposal t and the
    outcome 'lineage G falls by ≥ δ within t+1..t+3'."""
    G = [x["G"] for x in t.lineage]
    rows = []
    for r in t.records:
        g = r["generation"]
        future = G[g + 1: g + 1 + HORIZON]
        if not future:
            continue                        # no horizon left; undefined outcome
        outcome = min(future) <= G[g] - delta
        rows.append({"trajectory": t.key, "generation": g, "outcome": bool(outcome), **signals_for(r)})
    return rows


def auroc_table(trajs: Sequence[Trajectory], delta: float, *, arms: Sequence[str] = ("B", "C"), B: int = 1000,
                lower_bound_uninformative: float = 0.5) -> Dict[str, Dict[str, object]]:
    blocks = [outcome_rows(t, delta) for t in trajs if t.arm in arms]
    blocks = [b for b in blocks if b]
    table: Dict[str, Dict[str, object]] = {}
    for sig in PREREGISTERED:
        def stat(bs, sig=sig):
            rows = [r for b in bs for r in b]
            return auroc([r[sig] for r in rows], [r["outcome"] for r in rows])
        point = stat(blocks)
        lo, hi = block_bootstrap_ci(blocks, stat, B=B)
        table[sig] = {"auroc": point, "ci_low": lo, "ci_high": hi, "n_rows": sum(len(b) for b in blocks),
                      "n_trajectories": len(blocks), "positives": sum(r["outcome"] for b in blocks for r in b),
                      "uninformative": (lo is not None and lo <= lower_bound_uninformative) if point is not None else None}
    return table


def lead_times(trajs: Sequence[Trajectory], delta: float, thresholds: Dict[str, float]) -> Dict[str, List[Optional[int]]]:
    """Generations between the first exceedance of a signal's threshold and the
    onset generation, per trajectory with a defined onset."""
    from analysis.trajectory import onset_generation
    out: Dict[str, List[Optional[int]]] = {s: [] for s in thresholds}
    for t in trajs:
        G = [x["G"] for x in t.lineage]
        P = [x["P_V"] for x in t.lineage]
        on = onset_generation(G, P, delta)
        if on is None:
            continue
        for sig, thr in thresholds.items():
            first = next((r["generation"] for r in t.records if (signals_for(r)[sig] or 0) >= thr), None)
            out[sig].append(None if first is None else on - first)
    return out


def within_trajectory_auroc(trajs: Sequence[Trajectory], delta: float, *, arms: Sequence[str] = ("B", "C")) -> Dict[str, Dict[str, object]]:
    """Secondary H5 analysis: AUROC computed inside each trajectory (only trajectories with both
    outcomes defined), then averaged, so between-arm differences cannot inflate the pooled figure."""
    table: Dict[str, Dict[str, object]] = {}
    per_traj = [outcome_rows(t, delta) for t in trajs if t.arm in arms]
    for sig in PREREGISTERED:
        vals = []
        for rows in per_traj:
            a = auroc([r[sig] for r in rows], [r["outcome"] for r in rows])
            if a is not None:
                vals.append(a)
        table[sig] = {"mean_auroc": (sum(vals) / len(vals)) if vals else None, "n_trajectories_with_both_outcomes": len(vals)}
    return table
