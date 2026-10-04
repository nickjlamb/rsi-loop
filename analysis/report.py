"""Run the frozen analysis on an artifact tree and write summary.json,
tables.md and figures.

    python3 -m analysis.report --run mock-001 --delta 0.02
    python3 -m analysis.report --run pilot-01 --artifacts artifacts --out analysis/out/pilot-01

δ is fixed at freeze (design D.9: twice the SE of G on H, computed in the pilot);
until then it must be passed explicitly so no default can quietly become the
preregistered value."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

from analysis import figures, hypotheses, monitorability, secondary
from analysis.load import Trajectory, load_run
from analysis.trajectory import decomposition, metrics_for
from optimizer.models import DEFAULT_TIER, STRONG_TIER

ROOT = Path(__file__).resolve().parent.parent


def analyse(trajs: List[Trajectory], delta: float, *, bootstrap_B: int = 1000,
            default_model: str = DEFAULT_TIER, strong_model: str = STRONG_TIER,
            baseline_model: str = "parametric") -> Dict[str, object]:
    ms = [metrics_for(t, delta) for t in trajs]
    # The confirmatory core (H1–H5) and the secondary analyses 1–3 are defined on the primary set: default tier,
    # notes on, LLM optimiser. H6 and H7 add the strong-tier and notes-off factors; the baseline contrast adds
    # the parametric optimiser. (Analysis defect 4, 4 Oct 2026: the frozen report loaded one run id, so the
    # secondary factors, which live under their own run ids, could not reach H6/H7; scoping made explicit.)
    primary = [t for t in trajs if t.model == default_model and t.notes_enabled]
    return {
        "delta": delta, "n_trajectories": len(trajs), "n_primary": len(primary),
        "runs": sorted({t.run_id for t in trajs}),
        "trajectories": [m.to_dict() for m in ms],
        "decomposition": {t.key: decomposition(t) for t in trajs},
        "H1": hypotheses.H1_goodhart_curve(ms, model=default_model, notes=True),
        "H2": hypotheses.H2_hidden_holdout(ms, model=default_model, notes=True),
        "H3": hypotheses.H3_self_evaluation(ms, model=default_model, notes=True),
        "H4": hypotheses.H4_pressure_is_the_optimisers(ms, model=default_model, notes=True),
        "H5": monitorability.auroc_table(primary, delta, B=bootstrap_B),
        "H6": hypotheses.H6_capability(ms, default_model, strong_model),
        "H7": hypotheses.H7_recursive_channel(ms, model=default_model),
        "H5_within_trajectory": monitorability.within_trajectory_auroc(primary, delta),
        "H5_lead_times": monitorability.lead_times(primary, delta, monitorability.LEAD_TIME_THRESHOLDS),
        "secondary": {"accuracy_gate_counterfactual": {k: v for k, v in secondary.accuracy_gate_counterfactual(primary).items() if k != "rows"},
                      "no_op_accounting": secondary.no_op_accounting(trajs),
                      "protocol_failure_rates": secondary.protocol_failure_rates(trajs),
                      "baseline_contrast": secondary.baseline_contrast(ms, llm_model=default_model, baseline_model=baseline_model)},
    }


def tables_md(summary: Dict[str, object]) -> str:
    rows = ["# Analysis summary", "", f"δ = {summary['delta']}, trajectories = {summary['n_trajectories']}", "",
            "## Per trajectory", "", "| arm | seed | model | notes | G0 | G_final | G_max | G_AUC | P_final | Δ_final | Δ_slope | onset | accepted (changes) | env viol (prop) | tamper | cost |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    f = lambda x: "—" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))
    for m in summary["trajectories"]:
        rows.append(f"| {m['arm']} | {m['seed']} | {m['model']} | {'on' if m['notes_enabled'] else 'off'} | {f(m['G0'])} | {f(m['G_final'])} | "
                    f"{f(m['G_max'])} | {f(m['G_AUC'])} | {f(m['P_final'])} | {f(m['delta_final'])} | {f(m['delta_slope'])} | "
                    f"{f(m['onset'])} | {m['accepted']}/{m['n']} ({m['accepted_changes']}) | {f(m['proposal_envelope_violation_rate'])} | {m['tamper_events']} | ${m['cost_usd']:.2f} |")
    rows += ["", "## Hypotheses", ""]
    for h in ("H1", "H2", "H3", "H4", "H6", "H7"):
        rows.append(f"- **{h}**: {summary[h].get('verdict')}")
    rows += ["", "## H5 monitorability (arms B and C)", "", "| signal | AUROC | 95% CI | rows | positives | uninformative |", "|---|---|---|---|---|---|"]
    for sig, v in summary["H5"].items():
        rows.append(f"| {sig} | {f(v['auroc'])} | [{f(v['ci_low'])}, {f(v['ci_high'])}] | {v['n_rows']} | {v['positives']} | {v['uninformative']} |")
    bc = summary.get("secondary", {}).get("baseline_contrast") or {}
    if bc:
        rows += ["", "## Baseline contrast (LLM default tier vs parametric hill-climber, per arm)", "",
                 "| arm | G_AUC llm / base | G_final llm / base | Δ_final llm / base | changes llm / base | env viol llm / base | llm − base G_final HL [95% CI] |",
                 "|---|---|---|---|---|---|---|"]
        for arm, r in bc.items():
            hl = r.get("llm_minus_baseline_G_final_hl") or {}
            rows.append(f"| {arm} | {f(r['llm_G_AUC'])} / {f(r['baseline_G_AUC'])} | {f(r['llm_G_final'])} / {f(r['baseline_G_final'])} | "
                        f"{f(r['llm_delta_final'])} / {f(r['baseline_delta_final'])} | {f(r['llm_accepted_changes'])} / {f(r['baseline_accepted_changes'])} | "
                        f"{f(r['llm_proposal_envelope_violation_rate'])} / {f(r['baseline_proposal_envelope_violation_rate'])} | "
                        f"{f(hl.get('estimate'))} [{f(hl.get('ci_low'))}, {f(hl.get('ci_high'))}] |")
    for h in ("H6", "H7"):
        v = summary.get(h) or {}
        if v.get("verdict") not in (None, "n/a"):
            rows += ["", f"## {h} detail", "", "```", json.dumps({k: x for k, x in v.items()}, indent=1, default=str)[:4000], "```"]
    return "\n".join(rows) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, action="append",
                    help="run id under --artifacts; repeat to combine runs (primary + strong tier + notes-off + baseline)")
    ap.add_argument("--delta", type=float, required=True)
    ap.add_argument("--artifacts", type=Path, default=ROOT / "artifacts")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--default-model", default=DEFAULT_TIER, help="model id treated as the default tier (use 'scripted' for mock runs)")
    ap.add_argument("--strong-model", default=STRONG_TIER)
    a = ap.parse_args(argv)
    trajs = [t for r in a.run for t in load_run(a.artifacts / r)]
    if not trajs:
        print("no trajectories found under", [str(a.artifacts / r) for r in a.run], file=sys.stderr)
        return 1
    out = a.out or (ROOT / "analysis" / "out" / "+".join(a.run))
    out.mkdir(parents=True, exist_ok=True)
    summary = analyse(trajs, a.delta, bootstrap_B=a.bootstrap, default_model=a.default_model, strong_model=a.strong_model)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
    (out / "tables.md").write_text(tables_md(summary))
    from analysis.trajectory import metrics_for as mf
    ms = [mf(t, a.delta) for t in trajs]
    (out / "figures").mkdir(exist_ok=True)
    figures.lineage_curves(ms, out / "figures" / "G_lineage.png", "G_lineage", "Hidden ground truth of the accepted lineage")
    figures.lineage_curves(ms, out / "figures" / "P_lineage.png", "P_lineage", "Visible accuracy of the accepted lineage")
    figures.auroc_bars(summary["H5"], out / "figures" / "monitorability.png")
    print("wrote", out)
    print((out / "tables.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
