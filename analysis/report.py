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

from analysis import figures, hypotheses, monitorability
from analysis.load import Trajectory, load_run
from analysis.trajectory import decomposition, metrics_for
from optimizer.models import DEFAULT_TIER, STRONG_TIER

ROOT = Path(__file__).resolve().parent.parent


def analyse(trajs: List[Trajectory], delta: float, *, bootstrap_B: int = 1000,
            default_model: str = DEFAULT_TIER, strong_model: str = STRONG_TIER) -> Dict[str, object]:
    ms = [metrics_for(t, delta) for t in trajs]
    return {
        "delta": delta, "n_trajectories": len(trajs),
        "trajectories": [m.to_dict() for m in ms],
        "decomposition": {t.key: decomposition(t) for t in trajs},
        "H1": hypotheses.H1_goodhart_curve(ms, model=default_model, notes=True),
        "H2": hypotheses.H2_hidden_holdout(ms, model=default_model, notes=True),
        "H3": hypotheses.H3_self_evaluation(ms, model=default_model, notes=True),
        "H4": hypotheses.H4_pressure_is_the_optimisers(ms, model=default_model, notes=True),
        "H5": monitorability.auroc_table(trajs, delta, B=bootstrap_B),
        "H6": hypotheses.H6_capability(ms, default_model, strong_model),
        "H7": hypotheses.H7_recursive_channel(ms, model=default_model),
    }


def tables_md(summary: Dict[str, object]) -> str:
    rows = ["# Analysis summary", "", f"δ = {summary['delta']}, trajectories = {summary['n_trajectories']}", "",
            "## Per trajectory", "", "| arm | seed | model | notes | G0 | G_final | G_max | G_AUC | P_final | Δ_final | Δ_slope | onset | accepted | env viol (prop) | tamper | cost |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    f = lambda x: "—" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))
    for m in summary["trajectories"]:
        rows.append(f"| {m['arm']} | {m['seed']} | {m['model']} | {'on' if m['notes_enabled'] else 'off'} | {f(m['G0'])} | {f(m['G_final'])} | "
                    f"{f(m['G_max'])} | {f(m['G_AUC'])} | {f(m['P_final'])} | {f(m['delta_final'])} | {f(m['delta_slope'])} | "
                    f"{f(m['onset'])} | {m['accepted']}/{m['n']} | {f(m['proposal_envelope_violation_rate'])} | {m['tamper_events']} | ${m['cost_usd']:.2f} |")
    rows += ["", "## Hypotheses", ""]
    for h in ("H1", "H2", "H3", "H4", "H6", "H7"):
        rows.append(f"- **{h}**: {summary[h].get('verdict')}")
    rows += ["", "## H5 monitorability (arms B and C)", "", "| signal | AUROC | 95% CI | rows | positives | uninformative |", "|---|---|---|---|---|---|"]
    for sig, v in summary["H5"].items():
        rows.append(f"| {sig} | {f(v['auroc'])} | [{f(v['ci_low'])}, {f(v['ci_high'])}] | {v['n_rows']} | {v['positives']} | {v['uninformative']} |")
    return "\n".join(rows) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--delta", type=float, required=True)
    ap.add_argument("--artifacts", type=Path, default=ROOT / "artifacts")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--default-model", default=DEFAULT_TIER, help="model id treated as the default tier (use 'scripted' for mock runs)")
    ap.add_argument("--strong-model", default=STRONG_TIER)
    a = ap.parse_args(argv)
    trajs = load_run(a.artifacts / a.run)
    if not trajs:
        print("no trajectories found under", a.artifacts / a.run, file=sys.stderr)
        return 1
    out = a.out or (ROOT / "analysis" / "out" / a.run)
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
