"""One trajectory: 20 revisions of an arm on a seed, with per-generation
persistence and resume-from-artifact.

    python3 -m loop.run --run-id mock-001 --arm B --seed 1 --mock
    python3 -m loop.run --run-id pilot-01 --arm D --seed 1 --model anthropic/claude-sonnet-5

Artifact layout (design E.2):

    artifacts/<run>/arm_<X>/seed_<NNNN>/
        trajectory.json                config, model, prompt hashes, harness SHA, per-generation summary, totals
        gen_00/scores.json             the initial policy's full score bundle
        gen_NN/policy.py               the proposal (empty file if the revision produced none)
        gen_NN/notes.md                the proposal's notes
        gen_NN/diff.patch              unified diff against the parent version
        gen_NN/call.json               the full revision record: every prompt and completion, tool calls, usage, cost
        gen_NN/scores.json             the proposal's score bundle, the gate decision, the self-report discrepancy
        gen_NN/events.jsonl            denied sandbox events
        gen_NN/timing.json             wall-clock only (excluded from the resume-identity test)
        gen_NN/DONE                    written last; a generation without it is re-run on resume

An infrastructure failure (provider error after retries) is NOT a proposal
(design D.7): nothing is persisted for that generation, the failure is listed
in trajectory.json["infrastructure_failures"], the trajectory halts, and
re-running the same command resumes at that generation.

Resume: a generation with DONE is loaded, never re-run; the loop carries on
from the last completed one. Kill-and-resume therefore reproduces the same
tree for a deterministic optimiser and never loses a paid completion.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from env import datasets as dsm
from evaluator import visible as visible_mod
from evaluator.bundle import ScoreBundle, invalid_bundle, score_candidate
from loop import freeze
from loop.config import RunConfig
from loop.gates import GateDecision, decide
from optimizer import agent, context
from optimizer.providers import PerplexityAgentProvider, Provider, ScriptedProvider
from optimizer.tools import ToolBox
from sandbox.runner import SandboxResult

ROOT = Path(__file__).resolve().parent.parent
HARNESS_VERSION = "0.1.0"


def harness_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _dump(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, default=str) + "\n")


def _load(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text())


def _stable(bundle_dict: Dict[str, object]) -> Dict[str, object]:
    """scores.json must be byte-identical across a kill-and-resume; wall-clock goes to timing.json."""
    d = dict(bundle_dict)
    d.pop("elapsed_s", None)
    return d


@dataclass
class GenerationSummary:
    generation: int
    outcome: str
    accepted: bool
    category: str
    P_V: Optional[float]
    P_Hprime: Optional[float]
    G: Optional[float]
    envelope_inside: Optional[bool]
    canary_passed: Optional[bool]
    denied_events: int
    guard_violations: int
    local_evals: int
    cost_usd: float
    self_report_discrepancy: Optional[float] = None


@dataclass
class TrajectoryState:
    current_source: str
    current_notes: str
    current_bundle: ScoreBundle
    lineage: List[context.LineageEntry] = field(default_factory=list)
    summaries: List[GenerationSummary] = field(default_factory=list)
    cost_usd: float = 0.0
    halted: Optional[str] = None


def _bundle_from_dict(d: Dict[str, object]) -> ScoreBundle:
    keys = set(ScoreBundle.__dataclass_fields__)
    return ScoreBundle(**{k: v for k, v in d.items() if k in keys})


def _missing_bundle(reason: str) -> ScoreBundle:
    res = SandboxResult(valid=False, reason=reason, predictions=[], metrics=[], guard={})
    return invalid_bundle(res)


def make_provider(cfg: RunConfig, scripted_replies=None) -> Provider:
    if cfg.provider == "scripted" or cfg.mock:
        if scripted_replies is None:
            from loop.mock_optimiser import ScriptedOptimiser
            scripted_replies = [ScriptedOptimiser(cfg.arm)] * (cfg.generations * 6)
        return ScriptedProvider(scripted_replies)
    key = os.environ.get("PERPLEXITY_API_KEY", "")
    return PerplexityAgentProvider(key)


def run_trajectory(cfg: RunConfig, provider: Optional[Provider] = None, *, quiet: bool = False) -> TrajectoryState:
    freeze.check_seed(cfg.seed, mock=cfg.mock)
    provider = provider or make_provider(cfg)
    ds = dsm.build(cfg.seed)
    V_public = [f.public() for f in ds.V]
    tdir = cfg.trajectory_dir
    tdir.mkdir(parents=True, exist_ok=True)
    eval_src = (ROOT / "evaluator" / "visible.py").read_text() if cfg.eval_source_visible else None
    tools = ToolBox(run_visible_eval=lambda s: visible_mod.evaluate(s, V_public, cfg.visible_detail).to_dict(),
                    max_local_evals=cfg.max_local_evals)

    # generation 0: the initial policy, scored
    gen0_src = (ROOT / "policy" / "policy_v0.py").read_text()
    g0 = tdir / "gen_00"
    if (g0 / "DONE").exists():
        b0 = _bundle_from_dict(_load(g0 / "scores.json")["bundle"])
    else:
        g0.mkdir(exist_ok=True)
        b0 = score_candidate(gen0_src, ds)
        (g0 / "policy.py").write_text(gen0_src)
        (g0 / "notes.md").write_text("")
        _dump(g0 / "scores.json", {"generation": 0, "bundle": _stable(b0.to_dict())})
        (g0 / "DONE").write_text("ok\n")
    state = TrajectoryState(current_source=gen0_src, current_notes="", current_bundle=b0)

    manifest = dsm.manifest(ds)
    traj = {"config": cfg.to_dict(), "harness_version": HARNESS_VERSION, "harness_sha": harness_sha(),
            "design_frozen": freeze.DESIGN_FROZEN, "freeze_tag": freeze.FREEZE_TAG,
            "prompt_hashes": context.prompt_hashes(), "dataset_manifest_sha": {k: v["sha256"] for k, v in manifest["sets"].items()},
            "provider": getattr(provider, "name", "unknown"), "gen0": {"P_V": b0.P_V, "P_Hprime": b0.P_Hprime, "G": b0.G,
                                                                        "envelope_inside": b0.envelope_inside},
            "generations": [], "totals": {}, "status": "running"}
    _dump(tdir / "trajectory.json", traj)

    for gen in range(1, cfg.generations + 1):
        gdir = tdir / f"gen_{gen:02d}"
        if (gdir / "DONE").exists():
            if _load(gdir / "scores.json").get("outcome") == "provider_failure":
                shutil.rmtree(gdir)          # an infrastructure failure is not a proposal (D.7); re-run it
            else:
                _resume_generation(state, gdir, gen)
                continue
        if state.halted:
            break
        if state.cost_usd >= cfg.max_cost_usd:
            state.halted = f"cost guard: {state.cost_usd:.2f} USD >= {cfg.max_cost_usd:.2f}"
            break
        gdir.mkdir(exist_ok=True)
        t0 = time.time()

        report = visible_mod.evaluate(state.current_source, V_public, cfg.visible_detail).to_dict()
        ctx = context.build(arm=cfg.arm, generation=gen, current_source=state.current_source, notes=state.current_notes,
                            lineage=state.lineage, V_public=V_public, report=report, notes_enabled=cfg.notes_enabled,
                            visible_detail=cfg.visible_detail, eval_source_visible=cfg.eval_source_visible,
                            visible_eval_source=eval_src)
        rec = agent.run_revision(ctx, provider, tools, model=cfg.model, max_output_tokens=cfg.max_output_tokens,
                                 temperature=cfg.temperature, require_self_report=(cfg.arm == "A"),
                                 cache_key=f"rsi-loop-2/{cfg.run_id}/{cfg.arm}/{cfg.seed}")
        t_model = time.time() - t0

        prop = rec.proposal
        if prop.outcome == "provider_failure":
            traj.setdefault("infrastructure_failures", []).append(
                {"generation": gen, "error": rec.error, "at": time.time(), "model_calls": rec.model_calls})
            state.halted = f"provider failure at generation {gen}: {rec.error}"
            shutil.rmtree(gdir, ignore_errors=True)
            if not quiet:
                print(f"[{cfg.run_id} {cfg.arm} seed {cfg.seed}] gen {gen:02d} INFRASTRUCTURE FAILURE (not a proposal; "
                      f"re-run this command to resume): {rec.error}")
            break
        bundle = _missing_bundle(prop.outcome) if prop.source is None else score_candidate(prop.source, ds)
        t_score = time.time() - t0 - t_model

        optimiser_accepts = prop.self_report.get("deploy") if cfg.arm == "A" else None
        if cfg.arm == "A" and optimiser_accepts is None:
            optimiser_accepts = False
        decision: GateDecision = decide(cfg.arm, bundle, state.current_bundle, optimiser_accepts)
        discrepancy = None
        if cfg.arm == "A" and prop.source is not None and "measured_visible_accuracy" in prop.self_report:
            discrepancy = abs(float(prop.self_report["measured_visible_accuracy"]) - bundle.P_V)

        # --- persist ----------------------------------------------------------
        (gdir / "policy.py").write_text(prop.source or "")
        (gdir / "notes.md").write_text(prop.notes or "")
        diff = "".join(difflib.unified_diff(state.current_source.splitlines(True), (prop.source or "").splitlines(True),
                                            fromfile=f"parent/policy.py", tofile=f"gen_{gen:02d}/policy.py"))
        (gdir / "diff.patch").write_text(diff)
        _dump(gdir / "call.json", rec.to_dict())
        _dump(gdir / "scores.json", {
            "generation": gen, "outcome": prop.outcome, "bundle": _stable(bundle.to_dict()),
            "decision": {"accepted": decision.accepted, "category": decision.category, "detail": decision.detail,
                         "optimiser_message": decision.optimiser_message},
            "self_report": prop.self_report, "self_report_discrepancy": discrepancy,
            "parent_generation": _parent_generation(state), "rationale": prop.rationale,
            "diff_lines": sum(1 for l in diff.splitlines() if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))),
        })
        with (gdir / "events.jsonl").open("w") as fh:
            for e in bundle.denied_events:
                fh.write(json.dumps({"kind": "denied", **e}) + "\n")
        _dump(gdir / "timing.json", {"model_s": round(t_model, 3), "score_s": round(t_score, 3), "sandbox_s": bundle.elapsed_s,
                                     "total_s": round(time.time() - t0, 3), "finished_at": time.time()})
        (gdir / "DONE").write_text("ok\n")

        _apply(state, gen, prop, bundle, decision, rec.local_evals, rec.cost_usd, discrepancy)
        if not quiet:
            print(f"[{cfg.run_id} {cfg.arm} seed {cfg.seed}] gen {gen:02d} {prop.outcome:16s} "
                  f"{'ACCEPT' if decision.accepted else 'reject':6s} {decision.category:14s} "
                  f"P_V={bundle.P_V:.3f} P_H'={bundle.P_Hprime:.3f} G={bundle.G:.3f} "
                  f"env={'in' if bundle.envelope_inside else 'OUT'} cost=${rec.cost_usd:.4f}")
        _write_trajectory(tdir, traj, state, cfg)

    traj["status"] = "halted" if state.halted else ("complete" if len(state.summaries) >= cfg.generations else "partial")
    traj["halted_reason"] = state.halted
    _write_trajectory(tdir, traj, state, cfg)
    return state


def _parent_generation(state: TrajectoryState) -> int:
    for e in reversed(state.lineage):
        if e.accepted:
            return e.generation
    return 0


def _apply(state, gen, prop, bundle, decision, local_evals, cost, discrepancy):
    state.lineage.append(context.LineageEntry(gen, decision.accepted, decision.category,
                                              bundle.P_V if bundle.sandbox_valid else None))
    state.summaries.append(GenerationSummary(
        generation=gen, outcome=prop.outcome, accepted=decision.accepted, category=decision.category,
        P_V=bundle.P_V if bundle.sandbox_valid else None, P_Hprime=bundle.P_Hprime if bundle.sandbox_valid else None,
        G=bundle.G if bundle.sandbox_valid else None, envelope_inside=bundle.envelope_inside if bundle.sandbox_valid else None,
        canary_passed=bundle.canary_passed if bundle.sandbox_valid else None, denied_events=bundle.denied_event_count,
        guard_violations=len((bundle.guard or {}).get("violations", []) or []), local_evals=local_evals, cost_usd=cost, self_report_discrepancy=discrepancy))
    state.cost_usd += cost
    if decision.accepted and prop.source is not None:
        state.current_source = prop.source
        state.current_bundle = bundle
    if prop.source is not None:
        state.current_notes = prop.notes    # notes persist whether or not the proposal was accepted


def _resume_generation(state: TrajectoryState, gdir: Path, gen: int) -> None:
    sc = _load(gdir / "scores.json")
    call = _load(gdir / "call.json")
    bundle = _bundle_from_dict(sc["bundle"])
    src = (gdir / "policy.py").read_text() or None
    notes = (gdir / "notes.md").read_text()
    prop = agent.Proposal(src, notes, sc.get("rationale", ""), sc.get("self_report", {}), sc["outcome"])
    decision = GateDecision(sc["decision"]["accepted"], sc["decision"]["category"], sc["decision"]["detail"])
    _apply(state, gen, prop, bundle, decision, int(call.get("local_evals", 0)), float(call.get("cost_usd", 0.0)),
           sc.get("self_report_discrepancy"))


def _write_trajectory(tdir: Path, traj: Dict[str, object], state: TrajectoryState, cfg: RunConfig) -> None:
    traj["generations"] = [asdict(s) for s in state.summaries]
    acc = [s for s in state.summaries if s.accepted]
    traj["totals"] = {"generations_done": len(state.summaries), "accepted": len(acc),
                      "cost_usd": round(state.cost_usd, 6), "final_P_V": state.current_bundle.P_V,
                      "final_G": state.current_bundle.G, "final_envelope_inside": state.current_bundle.envelope_inside,
                      "denied_events": sum(s.denied_events for s in state.summaries),
                      "guard_violations": sum(s.guard_violations for s in state.summaries), "halted": state.halted}
    _dump(tdir / "trajectory.json", traj)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--arm", required=True, choices=list("ABCD"))
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--model", default="scripted")
    ap.add_argument("--generations", type=int, default=20)
    ap.add_argument("--mock", action="store_true", help="scripted optimiser, no spend")
    ap.add_argument("--no-notes", action="store_true")
    ap.add_argument("--detail", choices=["aggregate", "per-case"], default="per-case")
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--max-cost-usd", type=float, default=10.0)
    ap.add_argument("--artifacts", type=Path, default=None)
    a = ap.parse_args(argv)
    cfg = RunConfig(run_id=a.run_id, arm=a.arm, seed=a.seed, model=a.model if not a.mock else "scripted",
                    provider="scripted" if a.mock else "perplexity-agent", generations=a.generations,
                    notes_enabled=not a.no_notes, visible_detail=a.detail, temperature=a.temperature,
                    max_cost_usd=a.max_cost_usd, mock=a.mock,
                    **({"artifacts_root": a.artifacts} if a.artifacts else {}))
    st = run_trajectory(cfg)
    print(json.dumps({"accepted": sum(s.accepted for s in st.summaries), "generations": len(st.summaries),
                      "cost_usd": round(st.cost_usd, 4), "final_G": st.current_bundle.G, "halted": st.halted}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
