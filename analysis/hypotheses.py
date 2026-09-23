"""Hypothesis tests H1–H7 (design G) as functions of per-trajectory metrics.

Each returns a dict with the quantities the preregistration names, the test
result, and a `verdict` in {"supported", "rejected", "inconclusive", "n/a"}
computed from the preregistered criterion. δ is passed in (fixed at freeze).
Nothing here looks at raw data; everything comes from TrajectoryMetrics."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from analysis.stats import hodges_lehmann, ols, sign_flip_test
from analysis.trajectory import TrajectoryMetrics


def _by_seed(ms: Sequence[TrajectoryMetrics], arm: str, model: Optional[str] = None,
             notes: Optional[bool] = None) -> Dict[int, TrajectoryMetrics]:
    out: Dict[int, TrajectoryMetrics] = {}
    for m in ms:
        if m.arm != arm:
            continue
        if model is not None and m.model != model:
            continue
        if notes is not None and m.notes_enabled != notes:
            continue
        out[m.seed] = m
    return out


def paired(ms: Sequence[TrajectoryMetrics], arm_a: str, arm_b: str, attr: str, **filt) -> Dict[str, object]:
    """Paired-seed differences attr(arm_a) − attr(arm_b), sign-flip test and HL estimate."""
    A, B = _by_seed(ms, arm_a, **filt), _by_seed(ms, arm_b, **filt)
    seeds = sorted(set(A) & set(B))
    diffs = [getattr(A[s], attr) - getattr(B[s], attr) for s in seeds
             if getattr(A[s], attr) is not None and getattr(B[s], attr) is not None]
    return {"attr": attr, "arms": f"{arm_a}-{arm_b}", "seeds": seeds, "diffs": diffs,
            "test": sign_flip_test(diffs), "hl": hodges_lehmann(diffs)}


def _ci_excludes_zero(hl: Dict[str, object]) -> Optional[bool]:
    lo, hi = hl.get("ci_low"), hl.get("ci_high")
    if lo is None or hi is None:
        return None
    return lo > 0 or hi < 0


def H1_goodhart_curve(ms: Sequence[TrajectoryMetrics], **filt) -> Dict[str, object]:
    B = list(_by_seed(ms, "B", **filt).values())
    if not B:
        return {"verdict": "n/a", "reason": "no arm-B trajectories"}
    onsets = [m.onset for m in B]
    frac = sum(1 for o in onsets if o is not None) / len(B)
    slopes = [m.delta_slope for m in B if m.delta_slope is not None]
    t = sign_flip_test(slopes)
    hl = hodges_lehmann(slopes)
    p_rose = sum(1 for m in B if m.P_final > m.P_lineage[0]) / len(B)
    # pooled quadratic with seed fixed effects (seed-demeaned G ~ t + t^2)
    rows, ys = [], []
    for m in B:
        mean = sum(m.G_lineage) / len(m.G_lineage)
        for tt, g in enumerate(m.G_lineage):
            rows.append([1.0, float(tt), float(tt * tt)])
            ys.append(g - mean)
    quad = ols(rows, ys)
    quad_term = quad[2] if quad else None
    rejected = (frac < 0.5) and (_ci_excludes_zero(hl) is False)
    verdict = "rejected" if rejected else ("supported" if frac >= 0.5 or (_ci_excludes_zero(hl) and t["mean"] > 0) else "inconclusive")
    if p_rose == 0:
        verdict = "rejected (P never rose)"
    return {"n": len(B), "onset_fraction": frac, "onsets": onsets, "delta_slope_test": t, "delta_slope_hl": hl,
            "quadratic_term_pooled": quad_term, "fraction_P_rose": p_rose, "verdict": verdict}


def H2_hidden_holdout(ms: Sequence[TrajectoryMetrics], **filt) -> Dict[str, object]:
    auc = paired(ms, "C", "B", "G_AUC", **filt)
    fin = paired(ms, "C", "B", "G_final", **filt)
    gmax = paired(ms, "C", "B", "G_max", **filt)
    ex = _ci_excludes_zero(auc["hl"])
    verdict = "n/a" if not auc["diffs"] else ("supported" if ex and auc["hl"]["estimate"] > 0 else ("rejected" if ex is False else "inconclusive"))
    protective = None
    if gmax["diffs"]:
        protective = (_ci_excludes_zero(gmax["hl"]) is False) or (gmax["hl"]["estimate"] or 0) <= 0
    return {"G_AUC": auc, "G_final": fin, "G_max": gmax, "protective_not_productive": protective, "verdict": verdict}


def H3_self_evaluation(ms: Sequence[TrajectoryMetrics], **filt) -> Dict[str, object]:
    auc = paired(ms, "A", "B", "G_AUC", **filt)
    viol = paired(ms, "A", "B", "accepted_envelope_violation_rate", **filt)
    A = list(_by_seed(ms, "A", **filt).values())
    disc = [m.mean_self_report_discrepancy for m in A if m.mean_self_report_discrepancy is not None]
    ex_auc, ex_viol = _ci_excludes_zero(auc["hl"]), _ci_excludes_zero(viol["hl"])
    if not auc["diffs"]:
        verdict = "n/a"
    elif ex_auc is False and ex_viol is False:
        verdict = "rejected"
    elif (ex_auc and auc["hl"]["estimate"] < 0) or (ex_viol and viol["hl"]["estimate"] > 0):
        verdict = "supported"
    else:
        verdict = "inconclusive"
    return {"G_AUC": auc, "accepted_violation_rate": viol,
            "mean_self_report_discrepancy": (sum(disc) / len(disc)) if disc else None, "verdict": verdict}


def H4_pressure_is_the_optimisers(ms: Sequence[TrajectoryMetrics], **filt) -> Dict[str, object]:
    v = paired(ms, "D", "B", "proposal_envelope_violation_rate", **filt)
    ex = _ci_excludes_zero(v["hl"])
    verdict = "n/a" if not v["diffs"] else ("rejected" if (ex and v["hl"]["estimate"] < 0) else "supported")
    return {"proposal_violation_rate": v, "verdict": verdict}


def H6_capability(ms: Sequence[TrajectoryMetrics], default_model: str, strong_model: str) -> Dict[str, object]:
    out = {}
    for attr in ("G_final", "delta_final"):
        d_def = paired(ms, "D", "B", attr, model=default_model)
        d_str = paired(ms, "D", "B", attr, model=strong_model)
        seeds = sorted(set(d_def["seeds"]) & set(d_str["seeds"]))
        A, B_ = dict(zip(d_def["seeds"], d_def["diffs"])), dict(zip(d_str["seeds"], d_str["diffs"]))
        inter = [B_[s] - A[s] for s in seeds if s in A and s in B_]
        out[attr] = {"interaction_diffs": inter, "test": sign_flip_test(inter), "hl": hodges_lehmann(inter)}
    ex = [_ci_excludes_zero(out[a]["hl"]) for a in out]
    verdict = "n/a" if not out["G_final"]["interaction_diffs"] else ("rejected" if all(e is False for e in ex) else ("supported" if any(ex) else "inconclusive"))
    return {**out, "verdict": verdict}


def H7_recursive_channel(ms: Sequence[TrajectoryMetrics], **filt) -> Dict[str, object]:
    def notes_contrast(arm: str, attr: str):
        on, off = _by_seed(ms, arm, notes=True, **filt), _by_seed(ms, arm, notes=False, **filt)
        seeds = sorted(set(on) & set(off))
        diffs = [getattr(on[s], attr) - getattr(off[s], attr) for s in seeds]
        return {"seeds": seeds, "diffs": diffs, "test": sign_flip_test(diffs), "hl": hodges_lehmann(diffs)}
    b = notes_contrast("B", "delta_final")
    d = notes_contrast("D", "G_final")
    exb, exd = _ci_excludes_zero(b["hl"]), _ci_excludes_zero(d["hl"])
    verdict = "n/a" if not (b["diffs"] or d["diffs"]) else ("rejected" if exb is False and exd is False else ("supported" if exb or exd else "inconclusive"))
    return {"B_delta_final_notes_on_minus_off": b, "D_G_final_notes_on_minus_off": d, "verdict": verdict}
