"""
RSI Loop validation harness — Validated edition.

Pipeline:
    1. Run `detector.assess` against every scenario in benchmarks.json and
       compute accuracy / precision / recall / F1.
    2. If accuracy >= ACCURACY_GATE, hand control to the regulatory Auditor,
       which checks the AI-tuned thresholds against the Clinical Gold
       Standard. This is what prevents reward hacking.
    3. Print a final RSI Loop status. Only COMPLETE when both stages pass.

Exit codes:
    0  COMPLETE      — Accurate AND Compliant.
    1  NOT_ACCURATE  — Benchmarks under the accuracy gate. Auditor not run.
    2  NOT_COMPLIANT — Accuracy passed but thresholds fall outside clinical
                       norms; the loop is suspected of reward-hacking.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import auditor
import detector

BENCHMARKS_PATH = Path(__file__).parent / "benchmarks.json"
LAST_RUN_PATH = Path(__file__).parent / "last_run.json"

ACCURACY_GATE: float = 0.90  # below this we skip the audit entirely


@dataclass
class CaseResult:
    scenario_id: str
    expected: str
    predicted: str
    forward_head_metric: float
    wrist_deviation_metric: float
    triggered_rules: List[str]
    notes: str

    @property
    def passed(self) -> bool:
        return self.expected == self.predicted


@dataclass
class Metrics:
    total: int
    correct: int
    accuracy: float
    precision: float
    recall: float
    f1: float

    @classmethod
    def from_results(cls, results: List[CaseResult]) -> "Metrics":
        total = len(results)
        correct = sum(1 for r in results if r.passed)
        tp = sum(1 for r in results if r.expected == "High Strain" and r.predicted == "High Strain")
        fp = sum(1 for r in results if r.expected == "Safe" and r.predicted == "High Strain")
        fn = sum(1 for r in results if r.expected == "High Strain" and r.predicted == "Safe")
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        return cls(
            total=total,
            correct=correct,
            accuracy=correct / total if total else 0.0,
            precision=precision,
            recall=recall,
            f1=f1,
        )


def run() -> int:
    console = Console()
    benchmarks = json.loads(BENCHMARKS_PATH.read_text())
    scenarios = benchmarks["scenarios"]

    results: List[CaseResult] = []
    for sc in scenarios:
        assessment = detector.assess(sc["landmarks"])
        results.append(
            CaseResult(
                scenario_id=sc["id"],
                expected=sc["label"],
                predicted=assessment.label,
                forward_head_metric=assessment.forward_head_metric,
                wrist_deviation_metric=assessment.wrist_deviation_metric,
                triggered_rules=list(assessment.triggered_rules),
                notes=sc.get("notes", ""),
            )
        )

    metrics = Metrics.from_results(results)
    _render_log(console, results, metrics)

    audit_report: Optional[auditor.AuditReport] = None
    accurate = metrics.accuracy >= ACCURACY_GATE

    if accurate:
        console.rule("[bold cyan]Stage 2 — Regulatory Audit")
        audit_report = auditor.run_audit()
        auditor.render_report(audit_report, console=console)
    else:
        console.print(
            f"[bold red]Accuracy {metrics.accuracy:.0%} is below the "
            f"{ACCURACY_GATE:.0%} gate — auditor skipped.[/]"
        )

    final_status, exit_code = _final_status(metrics, audit_report)
    _render_final(console, final_status)
    _persist(results, metrics, audit_report, final_status)
    return exit_code


def _final_status(
    metrics: Metrics, audit_report: Optional[auditor.AuditReport]
) -> tuple[str, int]:
    if metrics.accuracy < ACCURACY_GATE:
        return "NOT_ACCURATE", 1
    assert audit_report is not None
    if not audit_report.is_compliant:
        return "NOT_COMPLIANT", 2
    return "COMPLETE", 0


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_log(console: Console, results: List[CaseResult], metrics: Metrics) -> None:
    title = Text("THE RSI LOOP — Self-Improvement Log", style="bold magenta")
    console.print(Panel(title, expand=False, border_style="magenta"))

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Scenario", style="white", no_wrap=True)
    table.add_column("Expected")
    table.add_column("Predicted")
    table.add_column("Fwd-head", justify="right")
    table.add_column("Wrist-dev", justify="right")
    table.add_column("Triggered", style="yellow")
    table.add_column("Result", justify="center")

    for r in results:
        result_marker = Text("PASS", style="bold green") if r.passed else Text("FAIL", style="bold red")
        predicted_style = "green" if r.passed else "red"
        table.add_row(
            r.scenario_id,
            r.expected,
            Text(r.predicted, style=predicted_style),
            f"{r.forward_head_metric:+.3f}",
            f"{r.wrist_deviation_metric:+.3f}",
            ", ".join(r.triggered_rules) or "—",
            result_marker,
        )

    console.print(table)

    summary_style = "bold green" if metrics.accuracy == 1.0 else "bold red"
    summary = Text.assemble(
        ("Accuracy ",  "white"), (f"{metrics.accuracy:.0%}  ", summary_style),
        ("Precision ", "white"), (f"{metrics.precision:.0%}  ", summary_style),
        ("Recall ",    "white"), (f"{metrics.recall:.0%}  ", summary_style),
        ("F1 ",        "white"), (f"{metrics.f1:.2f}", summary_style),
    )
    console.print(Panel(summary, border_style=summary_style.split()[-1], expand=False))

    failed = [r for r in results if not r.passed]
    if failed:
        console.rule("[bold red]Failures requiring analysis")
        for r in failed:
            console.print(
                Panel(
                    Text.assemble(
                        (f"{r.scenario_id}\n", "bold"),
                        (f"  expected={r.expected}  predicted={r.predicted}\n", "white"),
                        (f"  fwd-head={r.forward_head_metric:+.3f}  wrist-dev={r.wrist_deviation_metric:+.3f}\n", "yellow"),
                        (f"  notes: {r.notes}", "italic dim"),
                    ),
                    border_style="red",
                    expand=False,
                )
            )


_FINAL_STYLES = {
    "COMPLETE":       "bold green",
    "NOT_ACCURATE":   "bold red",
    "NOT_COMPLIANT":  "bold yellow",
}


def _render_final(console: Console, status: str) -> None:
    style = _FINAL_STYLES[status]
    msg = {
        "COMPLETE": "Accurate AND compliant — the validated RSI Loop is COMPLETE.",
        "NOT_ACCURATE": "Benchmarks under the accuracy gate; improve detector and re-run.",
        "NOT_COMPLIANT": "Thresholds fall outside clinical norms — possible reward hacking. Reject this iteration.",
    }[status]
    console.print(Panel(Text(f"RSI LOOP STATUS: {status}\n{msg}", style=style),
                        border_style=style.split()[-1], expand=False))


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _persist(
    results: List[CaseResult],
    metrics: Metrics,
    audit_report: Optional[auditor.AuditReport],
    final_status: str,
) -> None:
    payload = {
        "final_status": final_status,
        "metrics": asdict(metrics),
        "results": [asdict(r) for r in results],
        "audit": (
            {
                "overall": audit_report.overall,
                "findings": [asdict(f) for f in audit_report.findings],
            }
            if audit_report is not None
            else None
        ),
    }
    LAST_RUN_PATH.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    sys.exit(run())
