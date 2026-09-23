"""One revision of the optimiser: context → model → (eval ↔ model)* → proposal.

    rec = run_revision(ctx, provider, tools, model=..., require_self_report=(arm == "A"))

`rec` holds the proposal (source, notes, rationale, arm-A self report), the
full transcript (every prompt and completion, verbatim), the number of local
evaluations used, token usage, cost, latency and the prompt hashes. A reply
that cannot be parsed gets exactly one correction; a second failure, or an
exhausted eval budget without a submit, ends the revision with the outcome
recorded (design D.7: a failed proposal, never an exclusion).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from optimizer import protocol
from optimizer.context import Context
from optimizer.providers import Completion, Provider, ProviderError
from optimizer.tools import ToolBox

MAX_CORRECTIONS = 1


@dataclass
class Proposal:
    source: Optional[str]              # None when the revision produced no usable candidate
    notes: str
    rationale: str
    self_report: Dict[str, object]     # arm A only: {"deploy": bool, "measured_visible_accuracy": float}
    outcome: str                       # "submitted" | "forced_submit" | "protocol_failure" | "provider_failure"


@dataclass
class RevisionRecord:
    proposal: Proposal
    transcript: List[Dict[str, object]] = field(default_factory=list)   # role/content, plus tool results
    local_evals: int = 0
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    prompt_hashes: Dict[str, str] = field(default_factory=dict)
    context_meta: Dict[str, object] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        d = self.__dict__.copy()
        d["proposal"] = self.proposal.__dict__.copy()
        return d


def _account(rec: RevisionRecord, c: Completion) -> None:
    rec.model_calls += 1
    u = c.usage or {}
    rec.input_tokens += int(u.get("input_tokens") or u.get("prompt_tokens") or 0)
    rec.output_tokens += int(u.get("output_tokens") or u.get("completion_tokens") or 0)
    rec.cost_usd += float(c.cost_usd or 0.0)
    rec.latency_s += float(c.latency_s or 0.0)


def _eval_message(report: Dict[str, object], n_used: int, n_max: int) -> str:
    head = {k: report.get(k) for k in ("P", "n", "correct", "confusion", "sandbox_valid", "sandbox_reason", "frame_errors")}
    lines = [f"Visible evaluator report on your draft (local evaluation {n_used} of {n_max}):",
             str(head)]
    if report.get("per_case"):
        wrong = [r for r in report["per_case"] if not r.get("correct")]
        lines.append(f"Wrong cases ({len(wrong)}):")
        for r in wrong:
            lines.append(f"  {r['id']}: expected {r['expected']}, predicted {r['predicted']}")
    if n_used >= n_max:
        lines.append("You have no local evaluations left: your next reply must use \"action\": \"submit\".")
    return "\n".join(lines)


def run_revision(ctx: Context, provider: Provider, tools: ToolBox, *, model: str, max_output_tokens: int = 8000,
                 temperature: Optional[float] = None, require_self_report: bool = False) -> RevisionRecord:
    messages: List[Dict[str, str]] = ctx.messages()
    rec = RevisionRecord(proposal=Proposal(None, "", "", {}, "protocol_failure"), prompt_hashes=dict(ctx.prompt_hashes),
                         context_meta=ctx.to_dict())
    rec.transcript.extend({"role": m["role"], "content": m["content"]} for m in messages)
    corrections = 0
    last_parsed: Optional[protocol.ParsedReply] = None
    t0 = time.time()
    while True:
        try:
            c = provider.complete(messages, model=model, max_output_tokens=max_output_tokens, temperature=temperature)
        except ProviderError as e:
            rec.error = str(e)
            rec.proposal = Proposal(None, "", "", {}, "provider_failure")
            break
        _account(rec, c)
        messages.append({"role": "assistant", "content": c.text})
        rec.transcript.append({"role": "assistant", "content": c.text, "model": c.model, "usage": c.usage,
                               "cost_usd": c.cost_usd, "latency_s": c.latency_s, "response_id": c.response_id})
        parsed = protocol.parse(c.text, require_self_report=require_self_report)
        if not parsed.ok:
            if corrections < MAX_CORRECTIONS:
                corrections += 1
                msg = protocol.correction_message(parsed.error or "unparseable")
                messages.append({"role": "user", "content": msg})
                rec.transcript.append({"role": "user", "content": msg, "kind": "correction"})
                continue
            rec.error = f"protocol failure after correction: {parsed.error}"
            rec.proposal = Proposal(None, "", "", {}, "protocol_failure")
            break
        last_parsed = parsed
        if parsed.action == "run_visible_eval" and rec.local_evals < tools.max_local_evals:
            rec.local_evals += 1
            report = tools.run_visible_eval(parsed.source or "")
            msg = _eval_message(report, rec.local_evals, tools.max_local_evals)
            messages.append({"role": "user", "content": msg})
            rec.transcript.append({"role": "user", "content": msg, "kind": "tool_result",
                                   "tool": "run_visible_eval", "P": report.get("P")})
            continue
        outcome = "submitted" if parsed.action == "submit" else "forced_submit"
        rec.proposal = Proposal(parsed.source, parsed.notes, parsed.rationale, dict(parsed.extra), outcome)
        break
    rec.latency_s = round(time.time() - t0, 3) if rec.latency_s == 0 else rec.latency_s
    return rec
