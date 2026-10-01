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
