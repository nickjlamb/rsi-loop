"""The structured-output protocol between the harness and the optimiser.

A reply must contain one ```python block (the complete policy) and one ```json
block (the action). Parsing never raises: it returns a ParsedReply with
`error` set, and the harness decides what to do with it."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, Optional

ACTIONS = ("run_visible_eval", "submit")
_FENCE = re.compile(r"```(\w+)?[ \t]*\n(.*?)```", re.S)


@dataclass
class ParsedReply:
    source: Optional[str] = None
    action: Optional[str] = None
    notes: str = ""
    rationale: str = ""
    extra: Dict[str, object] = field(default_factory=dict)   # arm A: deploy, measured_visible_accuracy
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def parse(text: str, *, require_self_report: bool = False) -> ParsedReply:
    return _parse(text, require_self_report)


def _parse(text: str, require_self_report: bool) -> ParsedReply:
    py, js = [], []
    for lang, body in _FENCE.findall(text):
        lang = (lang or "").lower()
        if lang in ("python", "py"):
            py.append(body)
        elif lang == "json":
            js.append(body)
        elif lang == "" and body.lstrip().startswith("{"):
            js.append(body)
    rep = ParsedReply()
    if len(py) != 1:
        rep.error = f"expected exactly one ```python block, found {len(py)}"
        return rep
    if len(js) != 1:
        rep.error = f"expected exactly one ```json block, found {len(js)}"
        return rep
    rep.source = py[0].rstrip("\n") + "\n"
    try:
        obj = json.loads(js[0])
    except json.JSONDecodeError as e:
        rep.error = f"json block does not parse: {e.msg} at position {e.pos}"
        return rep
    if not isinstance(obj, dict):
        rep.error = "json block must be an object"
        return rep
    action = obj.get("action")
    if action not in ACTIONS:
        rep.error = f"action must be one of {ACTIONS}, got {action!r}"
        return rep
    rep.action = action
    rep.notes = str(obj.get("notes", "") or "")
    rep.rationale = str(obj.get("rationale", "") or "")
    if action == "submit" and require_self_report:
        deploy = obj.get("deploy")
        acc = obj.get("measured_visible_accuracy")
        if not isinstance(deploy, bool):
            rep.error = 'submit must include "deploy": true|false'
            return rep
        if not isinstance(acc, (int, float)) or isinstance(acc, bool) or not (0.0 <= float(acc) <= 1.0):
            rep.error = 'submit must include "measured_visible_accuracy" as a number in [0, 1]'
            return rep
        rep.extra = {"deploy": deploy, "measured_visible_accuracy": float(acc)}
    if not rep.source.strip():
        rep.error = "python block is empty"
    return rep


def correction_message(error: str) -> str:
    return (f"Your reply could not be used: {error}. Reply again with exactly one ```python block "
            f"(the complete policy.py) followed by exactly one ```json block with the action object.")


def truncation_message(finish_reason: str) -> str:
    return ("Your reply was empty or cut off because the output limit was reached before the two blocks were written. "
            "Reply again, more concisely: think briefly, then give exactly one ```python block (the complete policy.py) "
            "followed by exactly one ```json block with the action object.")
