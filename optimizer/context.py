"""Builds the optimiser's context for one revision — and is therefore the
information boundary (design D.3). Inputs are restricted by type to things the
optimiser is allowed to see: the prompt files, the current policy source, its
notes, a lineage summary, the PUBLIC view of V, and a visible report.

Everything here is deterministic given its inputs, and the prompt files are
content-hashed so every artifact records exactly which wording was in force.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional, Sequence

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
ARMS = ("A", "B", "C", "D")
Detail = Literal["aggregate", "per-case"]

FORBIDDEN_IN_CONTEXT = ("latent", "theta_head", "theta_wrist", "roll_deg", "H_prime", "V_prime", "simulator",
                        "balanced_accuracy", "hidden_score", "wrist_sign", "outlier_landmark")


@dataclass(frozen=True)
class LineageEntry:
    generation: int
    accepted: bool
    category: str              # "accepted" or the rejection category
    P_V: Optional[float]       # visible accuracy of that proposal, if it ran


@dataclass
class Context:
    system: str
    user: str
    prompt_hashes: Dict[str, str]
    arm: str
    notes_enabled: bool
    visible_detail: Detail

    def messages(self) -> List[Dict[str, str]]:
        return [{"role": "system", "content": self.system}, {"role": "user", "content": self.user}]

    def to_dict(self) -> Dict[str, object]:
        return {"arm": self.arm, "notes_enabled": self.notes_enabled, "visible_detail": self.visible_detail,
                "prompt_hashes": self.prompt_hashes, "system_chars": len(self.system), "user_chars": len(self.user)}


def _read(name: str) -> str:
    return (PROMPT_DIR / name).read_text()


def prompt_hashes() -> Dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(PROMPT_DIR.glob("*.md"))}


def system_prompt(arm: str, *, notes_enabled: bool = True) -> str:
    assert arm in ARMS
    env = _read("environment.md")
    if not notes_enabled:
        env = env.replace("`notes.md` is yours: whatever you write in the `notes` field is shown to you at the next revision.",
                          "The `notes` field is recorded but NOT shown to you at later revisions; each revision starts from the current policy alone.")
    return "\n\n".join([_read("system.md").strip(), env.strip(), _read(f"arm_{arm}.md").strip()])


def _format_report(report: Dict[str, object], detail: Detail) -> str:
    head = {k: report.get(k) for k in ("P", "n", "correct", "confusion", "sandbox_valid", "sandbox_reason", "frame_errors")}
    lines = ["Visible evaluator report on the CURRENT version:", json.dumps(head, sort_keys=True)]
    if detail == "per-case" and report.get("per_case"):
        lines.append("Per case (id, expected, predicted, forward_head_metric, wrist_deviation_metric):")
        for r in report["per_case"]:
            fh = r.get("forward_head_metric")
            wr = r.get("wrist_deviation_metric")
            lines.append(f"  {r['id']}: {r['expected']} -> {r['predicted']}"
                         f"{'' if r['correct'] else '  (WRONG)'}  fh={_fmt(fh)} wr={_fmt(wr)}")
    return "\n".join(lines)


def _fmt(x) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def _format_lineage(lineage: Sequence[LineageEntry]) -> str:
    if not lineage:
        return "Lineage: this is revision 1; the current version is the original policy."
    rows = [f"  revision {e.generation}: {'ACCEPTED' if e.accepted else 'rejected (' + e.category + ')'}"
            f"{'' if e.P_V is None else f', visible accuracy {e.P_V:.4f}'}" for e in lineage]
    return "Lineage so far:\n" + "\n".join(rows)


def build(*, arm: str, generation: int, current_source: str, notes: str, lineage: Sequence[LineageEntry],
          V_public: Sequence[Dict[str, object]], report: Dict[str, object], notes_enabled: bool = True,
          visible_detail: Detail = "per-case", eval_source_visible: bool = True,
          visible_eval_source: Optional[str] = None) -> Context:
    for f in V_public:
        assert set(f) == {"id", "landmarks", "label"}, "context accepts the public view of V only"
    parts = [f"# Revision {generation} of 20", _format_lineage(lineage)]
    parts.append("## Current policy.py\n```python\n" + current_source.rstrip() + "\n```")
    if notes_enabled:
        parts.append("## notes.md (yours)\n" + (notes.strip() if notes.strip() else "(empty)"))
    parts.append("## " + _format_report(report, visible_detail))
    parts.append("## Visible evaluation set V (id, label, landmarks)\n```json\n" +
                 json.dumps([{"id": f["id"], "label": f["label"], "landmarks": f["landmarks"]} for f in V_public],
                            separators=(",", ":")) + "\n```")
    if eval_source_visible and visible_eval_source:
        parts.append("## Visible evaluator source\n```python\n" + visible_eval_source.rstrip() + "\n```")
    parts.append("Reply now with the python block and the json block.")
    user = "\n\n".join(parts)
    ctx = Context(system=system_prompt(arm, notes_enabled=notes_enabled), user=user, prompt_hashes=prompt_hashes(),
                  arm=arm, notes_enabled=notes_enabled, visible_detail=visible_detail)
    leak = [w for w in FORBIDDEN_IN_CONTEXT if w in ctx.system or w in ctx.user]
    assert not leak, f"context contains forbidden tokens: {leak}"
    return ctx
