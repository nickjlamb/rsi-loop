"""Read an artifact tree into flat generation records and per-trajectory lineages.

    trajs = load_run(Path("artifacts") / "pilot-01")
    trajs[0].records[3]["G"]           # proposal-level
    trajs[0].lineage[3]["G"]           # accepted-lineage-level after generation 3
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Trajectory:
    run_id: str
    arm: str
    seed: int
    model: str
    notes_enabled: bool
    status: str
    gen0: Dict[str, object]
    records: List[Dict[str, object]] = field(default_factory=list)    # one per proposal, generation 1..N
    lineage: List[Dict[str, object]] = field(default_factory=list)    # index t = state after generation t (index 0 = gen 0)

    @property
    def key(self) -> str:
        return f"{self.arm}/{self.seed}/{self.model}/{'notes' if self.notes_enabled else 'nonotes'}"

    @property
    def n(self) -> int:
        return len(self.records)


def _load(p: Path) -> Dict[str, object]:
    return json.loads(p.read_text())


def _record(gen: int, sc: Dict[str, object], call: Dict[str, object], gdir_policy: str = "", parent_policy: str = "") -> Dict[str, object]:
    b = sc.get("bundle", {})
    valid = bool(b.get("sandbox_valid"))
    guard = b.get("guard") or {}
    return {
        "generation": gen, "outcome": sc.get("outcome"), "sandbox_valid": valid, "sandbox_reason": b.get("sandbox_reason"),
        "accepted": bool(sc["decision"]["accepted"]), "category": sc["decision"]["category"],
        "P_V": b.get("P_V") if valid else None, "P_Vprime": b.get("P_Vprime") if valid else None,
        "P_Hprime": b.get("P_Hprime") if valid else None, "G": b.get("G") if valid else None,
        "acc_H": b.get("acc_H") if valid else None,
        "envelope_inside": bool((b.get("envelope") or {}).get("inside")) if valid else None,
        "envelope_distance": (b.get("envelope") or {}).get("distance") if valid else None,
        "canary_passed": bool((b.get("canary") or {}).get("passed")) if valid else None,
        "denied_events": int(b.get("denied_event_count") or 0),
        "guard_violations": len(guard.get("violations") or []),
        "numeric_literal_count": guard.get("numeric_literal_count"),
        "literals_matching_V": b.get("literals_matching_V"),
        "V_correct": b.get("V_correct") or [], "H_correct_bits": b.get("H_correct_bits") or "",
        "diff_lines": sc.get("diff_lines"), "local_evals": call.get("local_evals", 0),
        "no_op": _is_no_op(gdir_policy, parent_policy),
        "cost_usd": call.get("cost_usd", 0.0), "input_tokens": call.get("input_tokens", 0),
        "output_tokens": call.get("output_tokens", 0),
        "self_report": sc.get("self_report") or {}, "self_report_discrepancy": sc.get("self_report_discrepancy"),
        "rationale": sc.get("rationale", ""),
    }


def _strip_docstrings_and_comments(src: str) -> str:
    """Functional content only: a proposal that changes nothing but prose is a no-op."""
    import ast
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree)


def _is_no_op(policy: str, parent: str) -> bool:
    if not policy or not parent:
        return False
    return _strip_docstrings_and_comments(policy) == _strip_docstrings_and_comments(parent)


def load_trajectory(tdir: Path) -> Trajectory:
    traj = _load(tdir / "trajectory.json")
    cfg = traj["config"]
    g0 = _load(tdir / "gen_00" / "scores.json")["bundle"]
    t = Trajectory(run_id=cfg["run_id"], arm=cfg["arm"], seed=int(cfg["seed"]), model=cfg["model"],
                   notes_enabled=bool(cfg.get("notes_enabled", True)), status=traj.get("status", "unknown"),
                   gen0={"P_V": g0["P_V"], "P_Vprime": g0["P_Vprime"], "P_Hprime": g0["P_Hprime"], "G": g0["G"],
                         "envelope_inside": bool(g0["envelope"]["inside"]), "H_correct_bits": g0.get("H_correct_bits", "")})
    cur = dict(t.gen0)
    t.lineage.append({"generation": 0, **cur})
    parent_src = (tdir / "gen_00" / "policy.py").read_text() if (tdir / "gen_00" / "policy.py").exists() else ""
    gen = 1
    while (tdir / f"gen_{gen:02d}" / "DONE").exists():
        gdir = tdir / f"gen_{gen:02d}"
        src = (gdir / "policy.py").read_text() if (gdir / "policy.py").exists() else ""
        rec = _record(gen, _load(gdir / "scores.json"), _load(gdir / "call.json"), src, parent_src)
        t.records.append(rec)
        if rec["accepted"] and rec["sandbox_valid"]:
            cur = {"P_V": rec["P_V"], "P_Vprime": rec["P_Vprime"], "P_Hprime": rec["P_Hprime"], "G": rec["G"],
                   "envelope_inside": rec["envelope_inside"], "H_correct_bits": rec["H_correct_bits"]}
            parent_src = src or parent_src
        t.lineage.append({"generation": gen, **cur})
        gen += 1
    return t


def load_run(run_dir: Path) -> List[Trajectory]:
    out: List[Trajectory] = []
    for tj in sorted(run_dir.glob("arm_*/seed_*/trajectory.json")):
        out.append(load_trajectory(tj.parent))
    return out
