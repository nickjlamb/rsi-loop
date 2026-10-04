"""Preregistered secondary analyses (experiments/preregistration.md §8)."""

from __future__ import annotations

from typing import Dict, List, Sequence

from analysis.load import Trajectory


def accuracy_gate_counterfactual(trajs: Sequence[Trajectory]) -> Dict[str, object]:
    """§8.1: in arms C and D, would an accuracy-scored hidden gate have decided differently?
    Walks each trajectory replaying the balanced-accuracy lineage, and asks per valid proposal
    whether accuracy on H' was non-decreasing against the current version."""
    rows: List[Dict[str, object]] = []
    for t in trajs:
        if t.arm not in ("C", "D"):
            continue
        cur_acc, cur_bal = t.gen0.get("P_Hprime"), None
        cur_G = t.gen0["G"]
        for r in t.records:
            if not r["sandbox_valid"] or r.get("bal_Hprime") is None:
                continue
            acc_ok = r["P_Hprime"] >= (cur_acc if cur_acc is not None else -1)
            rows.append({"trajectory": t.key, "generation": r["generation"], "accepted": r["accepted"],
                         "accuracy_gate_would_pass_hidden": acc_ok, "G_delta_vs_current": r["G"] - cur_G,
                         "category": r["category"]})
            if r["accepted"]:
                cur_acc, cur_G = r["P_Hprime"], r["G"]
    accepted = [x for x in rows if x["accepted"]]
    rejected_hidden = [x for x in rows if x["category"] == "hidden holdout"]
    return {
        "n_valid_proposals": len(rows),
        "accepted_that_accuracy_gate_would_also_pass": sum(1 for x in accepted if x["accuracy_gate_would_pass_hidden"]),
        "accepted_total": len(accepted),
        "rejected_by_hidden_that_accuracy_gate_would_have_passed": sum(1 for x in rejected_hidden if x["accuracy_gate_would_pass_hidden"]),
        "rejected_by_hidden_total": len(rejected_hidden),
        "mean_G_delta_of_those": (sum(x["G_delta_vs_current"] for x in rejected_hidden if x["accuracy_gate_would_pass_hidden"]) /
                                  max(1, sum(1 for x in rejected_hidden if x["accuracy_gate_would_pass_hidden"]))),
        "rows": rows,
    }


def no_op_accounting(trajs: Sequence[Trajectory]) -> Dict[str, Dict[str, object]]:
    """§8.2."""
    out = {}
    for t in trajs:
        acc = [r for r in t.records if r["accepted"]]
        out[t.key] = {"accepted": len(acc), "accepted_no_ops": sum(1 for r in acc if r.get("no_op")),
                      "proposals_no_ops": sum(1 for r in t.records if r.get("no_op"))}
    return out


def protocol_failure_rates(trajs: Sequence[Trajectory]) -> Dict[str, Dict[str, object]]:
    """§8.3, by model and arm."""
    out: Dict[str, Dict[str, object]] = {}
    for t in trajs:
        k = f"{t.model}/{t.arm}"
        d = out.setdefault(k, {"proposals": 0, "protocol_failures": 0})
        d["proposals"] += t.n
        d["protocol_failures"] += sum(1 for r in t.records if r["outcome"] == "protocol_failure")
    for d in out.values():
        d["rate"] = d["protocol_failures"] / d["proposals"] if d["proposals"] else None
    return out


def baseline_contrast(ms: Sequence, *, llm_model: str, baseline_model: str = "parametric") -> Dict[str, Dict[str, object]]:
    """Preregistered secondary analysis 6: the parametric hill-climber against the LLM, per arm, descriptively.
    Reports per-arm means of G_AUC, G_final, Δ_final, accepted changes and proposal envelope-violation rate for
    both optimisers, and the paired (by seed) HL estimate of LLM − baseline on G_AUC and G_final."""
    from analysis.stats import hodges_lehmann
    out: Dict[str, Dict[str, object]] = {}
    for arm in "ABCD":
        llm = {m.seed: m for m in ms if m.arm == arm and m.model == llm_model and m.notes_enabled}
        base = {m.seed: m for m in ms if m.arm == arm and m.model == baseline_model}
        if not llm or not base:
            continue
        def mean(d, attr):
            xs = [getattr(m, attr) for m in d.values() if getattr(m, attr) is not None]
            return (sum(xs) / len(xs)) if xs else None
        seeds = sorted(set(llm) & set(base))
        row: Dict[str, object] = {"n_llm": len(llm), "n_baseline": len(base), "paired_seeds": len(seeds)}
        for attr in ("G_AUC", "G_final", "delta_final", "accepted_changes", "proposal_envelope_violation_rate"):
            row[f"llm_{attr}"] = mean(llm, attr)
            row[f"baseline_{attr}"] = mean(base, attr)
        for attr in ("G_AUC", "G_final"):
            diffs = [getattr(llm[s], attr) - getattr(base[s], attr) for s in seeds
                     if getattr(llm[s], attr) is not None and getattr(base[s], attr) is not None]
            row[f"llm_minus_baseline_{attr}_hl"] = hodges_lehmann(diffs) if diffs else None
        out[arm] = row
    return out

