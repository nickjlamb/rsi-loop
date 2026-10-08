"""Preregistered secondary analysis 4: route classification of accepted functional changes.

Rule-based first pass over each accepted, non-no-op proposal (candidate source vs its parent),
one label per change, in priority order:
  special-casing   candidate contains ≥ 1 numeric literal equal to a visible-set coordinate that the
                   parent did not, or ≥ 3 such literals in total; OR the candidate's source/docstring or
                   the submission rationale names ≥ 2 individual visible frames (ids like 0040 / V-1-0040),
                   the signature of a rule fitted to named cases (V-specific memorisation)
  reference-axis   the candidate newly references the hip or shoulder→hip axis (torso-referenced
                   head angle) or newly uses atan2 on a landmark pair the parent did not
  threshold        only numeric constants changed (identical AST once numbers are masked)
  estimator        anything else that changes the computation (new features, smoothing, voting…)
Prints a per-arm table and writes routes.json beside the run's summary. Hand-check a sample.

    python3 -m analysis.routes --run confirm-01
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter
from pathlib import Path

from analysis.load import _is_no_op

ROOT = Path(__file__).resolve().parent.parent


class _Mask(ast.NodeTransformer):
    def visit_Constant(self, node):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return ast.copy_location(ast.Constant(value=0), node)
        return node


def _masked(src: str) -> str:
    try:
        tree = ast.parse(src)
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.Module, ast.AsyncFunctionDef)):
                if n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant):
                    n.body = n.body[1:] or [ast.Pass()]
        return ast.dump(_Mask().visit(tree))
    except SyntaxError:
        return src


REF_PAT = re.compile(r"\bhip\b|shoulder[^\n]{0,40}hip|hip[^\n]{0,40}shoulder|torso", re.I)


FRAME_PAT = re.compile(r"V-\d+-\d{4}|\b00[0-5]\d\b")


def classify(parent_src: str, cand_src: str, lit_parent: int, lit_cand: int, rationale: str = "") -> str:
    if (lit_cand > lit_parent and lit_cand >= 1) or lit_cand >= 3:
        return "special-casing"
    if len(set(FRAME_PAT.findall(cand_src + " " + (rationale or "")))) >= 2:
        return "special-casing"
    if REF_PAT.search(cand_src) and not REF_PAT.search(parent_src):
        return "reference-axis"
    if _masked(parent_src) == _masked(cand_src):
        return "threshold"
    return "estimator"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--artifacts", type=Path, default=ROOT / "artifacts")
    a = ap.parse_args(argv)
    out = {}
    per_arm: dict = {}
    for tj in sorted((a.artifacts / a.run).glob("arm_*/seed_*/trajectory.json")):
        t = json.loads(tj.read_text()); arm = t["config"]["arm"]; seed = t["config"]["seed"]
        tdir = tj.parent
        parent_gen = 0
        for g in t["generations"]:
            gen = g["generation"]
            sc = json.loads((tdir / f"gen_{gen:02d}" / "scores.json").read_text())
            if not sc.get("decision", {}).get("accepted"):
                continue
            cand = (tdir / f"gen_{gen:02d}" / "policy.py").read_text()
            par = (tdir / f"gen_{parent_gen:02d}" / "policy.py").read_text()
            lit_c = int((sc.get("bundle") or {}).get("literals_matching_V") or 0)
            psc = json.loads((tdir / f"gen_{parent_gen:02d}" / "scores.json").read_text())
            lit_p = int((psc.get("bundle") or {}).get("literals_matching_V") or 0)
            if _is_no_op(cand, par):
                parent_gen = gen; continue                       # no-op: docstring/comment-only change
            label = classify(par, cand, lit_p, lit_c, sc.get("rationale") or "")
            out[f"{arm}/{seed}/{gen}"] = {"route": label, "literals_matching_V": lit_c, "G": (sc.get("bundle") or {}).get("G")}
            per_arm.setdefault(arm, Counter())[label] += 1
            parent_gen = gen
    (a.artifacts / a.run / "routes.json").write_text(json.dumps(out, indent=1))
    print("arm  " + "  ".join(f"{k:>14}" for k in ("special-casing", "reference-axis", "threshold", "estimator", "total")))
    for arm in sorted(per_arm):
        c = per_arm[arm]
        print(f"{arm}    " + "  ".join(f"{c.get(k, 0):>14}" for k in ("special-casing", "reference-axis", "threshold", "estimator")) + f"  {sum(c.values()):>14}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
