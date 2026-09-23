"""Write a synthetic artifact tree with prescribed proposal outcomes, so the
analysis code can be validated (and its tests can assert exact answers)
before any real trajectory exists. Only the fields the loader reads are
written; the layout matches loop/run.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence


def _bundle(P_V: float, P_Vp: float, P_Hp: float, G: float, *, inside: bool = True, valid: bool = True,
            literals_matching: int = 0, denied: int = 0, guard_violations: Sequence[str] = (), V_correct: Optional[List[bool]] = None):
    return {"sandbox_valid": valid, "sandbox_reason": None if valid else "ast_guard", "denied_event_count": denied,
            "P_V": P_V, "P_Vprime": P_Vp, "P_Hprime": P_Hp, "G": G, "acc_H": G,
            "envelope": {"inside": inside, "distance": 0.0 if inside else 3.0, "thresholds": {}, "flips": {}, "errors": 0},
            "canary": {"passed": True, "n": 30, "failures": [], "crashes": []}, "frame_errors": {},
            "guard": {"ok": not guard_violations, "violations": list(guard_violations), "numeric_literal_count": 4 + literals_matching},
            "literals_matching_V": literals_matching, "V_correct": V_correct or [True] * int(round(P_V * 60)) + [False] * (60 - int(round(P_V * 60))),
            "H_correct_bits": ""}


def write_trajectory(root: Path, run_id: str, arm: str, seed: int, steps: Sequence[Dict[str, object]], *,
                     model: str = "synthetic", notes_enabled: bool = True,
                     gen0: Dict[str, float] = None) -> Path:
    """steps: one dict per generation with keys P_V, P_Vprime, P_Hprime, G, accepted, category,
    and optionally inside, valid, diff_lines, local_evals, literals_matching, denied, guard_violations, discrepancy."""
    gen0 = gen0 or {"P_V": 0.8667, "P_Vprime": 0.875, "P_Hprime": 0.75, "G": 0.747}
    tdir = root / run_id / f"arm_{arm}" / f"seed_{seed:04d}"
    (tdir / "gen_00").mkdir(parents=True, exist_ok=True)
    b0 = _bundle(gen0["P_V"], gen0["P_Vprime"], gen0["P_Hprime"], gen0["G"], inside=False)
    (tdir / "gen_00" / "scores.json").write_text(json.dumps({"generation": 0, "bundle": b0}))
    (tdir / "gen_00" / "DONE").write_text("ok\n")
    for i, s in enumerate(steps, start=1):
        g = tdir / f"gen_{i:02d}"
        g.mkdir(exist_ok=True)
        b = _bundle(s["P_V"], s["P_Vprime"], s["P_Hprime"], s["G"], inside=s.get("inside", True), valid=s.get("valid", True),
                    literals_matching=s.get("literals_matching", 0), denied=s.get("denied", 0),
                    guard_violations=s.get("guard_violations", ()), V_correct=s.get("V_correct"))
        (g / "scores.json").write_text(json.dumps({
            "generation": i, "outcome": s.get("outcome", "submitted"), "bundle": b,
            "decision": {"accepted": s["accepted"], "category": s["category"], "detail": "", "optimiser_message": ""},
            "self_report": s.get("self_report", {}), "self_report_discrepancy": s.get("discrepancy"),
            "parent_generation": 0, "rationale": "", "diff_lines": s.get("diff_lines", 5)}))
        (g / "call.json").write_text(json.dumps({"local_evals": s.get("local_evals", 1), "cost_usd": s.get("cost_usd", 0.1),
                                                 "input_tokens": 8000, "output_tokens": 2000}))
        (g / "DONE").write_text("ok\n")
    (tdir / "trajectory.json").write_text(json.dumps({
        "config": {"run_id": run_id, "arm": arm, "seed": seed, "model": model, "notes_enabled": notes_enabled},
        "status": "complete", "generations": [], "totals": {}}))
    return tdir


def goodhart_steps(n: int = 20, *, rise_until: int = 5, fall_from: int = 8, g0: float = 0.747, p0: float = 0.8667) -> List[Dict[str, object]]:
    """A canonical Goodhart trajectory: P rises monotonically; G rises, then falls after `fall_from`."""
    steps = []
    P, G = p0, g0
    for i in range(1, n + 1):
        P = min(1.0, P + 0.01)
        if i <= rise_until:
            G = G + 0.01
        elif i >= fall_from:
            G = G - 0.02
        steps.append({"P_V": round(P, 4), "P_Vprime": round(P - (0.05 if i >= fall_from else 0.0), 4),
                      "P_Hprime": round(G + 0.01, 4), "G": round(G, 4), "accepted": True, "category": "accepted",
                      "literals_matching": 10 if i >= fall_from - 1 else 0, "diff_lines": 5})
    return steps


def flat_steps(n: int = 20, *, g0: float = 0.747, p0: float = 0.8667) -> List[Dict[str, object]]:
    """Everything rejected: lineage never moves."""
    return [{"P_V": p0 - 0.02, "P_Vprime": p0 - 0.02, "P_Hprime": 0.7, "G": g0 - 0.01, "accepted": False,
             "category": "visible", "diff_lines": 5} for _ in range(n)]
