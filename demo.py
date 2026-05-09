"""
demo.py — the narrated, single-run tour of the RSI Loop.

Walks a reviewer through the full self-improvement arc in one terminal
session:

    1. Stage 1a — run the original v1 (intentionally flawed) detector against
       the benchmark suite. One scenario fails (radial wrist deviation).
    2. Self-correction narrative — explain the geometric flaw and the fix.
    3. Stage 1b — run the current v2 detector (imported from detector.py).
       All benchmarks pass.
    4. Stage 2 — invoke the regulatory Auditor against the v2 thresholds.
    5. Final status panel.

This is the recommended entry point for anyone reviewing the project. It
exercises the same code paths as `test_engine.py` but adds the narrative
panels and the v1 → v2 contrast.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Mapping, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

import auditor
import detector
from test_engine import (
    BENCHMARKS_PATH,
    CaseResult,
    Metrics,
    _final_status,
    _render_final,
    _render_log,
)


# ---------------------------------------------------------------------------
# v1 — the original, intentionally flawed detector, frozen here for the demo
# ---------------------------------------------------------------------------

V1_FORWARD_HEAD_OFFSET_THRESHOLD: float = 0.15
V1_WRIST_DEVIATION_OFFSET_THRESHOLD: float = 0.10


def v1_assess(landmarks: Mapping[str, Mapping[str, float]]) -> Tuple[str, float, float, Tuple[str, ...]]:
    """Frozen copy of the v1 logic: signed horizontal offsets, no angles."""
    fwd = landmarks["ear"]["x"] - landmarks["shoulder"]["x"]
    hand_center_x = (landmarks["index_mcp"]["x"] + landmarks["pinky_mcp"]["x"]) / 2.0
    wrist_dev = hand_center_x - landmarks["wrist"]["x"]
    triggered: List[str] = []
    if fwd > V1_FORWARD_HEAD_OFFSET_THRESHOLD:
        triggered.append("forward_head")
    if wrist_dev > V1_WRIST_DEVIATION_OFFSET_THRESHOLD:
        triggered.append("wrist_ulnar_deviation")
    label = "High Strain" if triggered else "Safe"
    return label, fwd, wrist_dev, tuple(triggered)


# ---------------------------------------------------------------------------
# Demo orchestration
# ---------------------------------------------------------------------------

def _to_results(
    scenarios: List[dict[str, Any]],
    assess_v1: bool,
) -> List[CaseResult]:
    results: List[CaseResult] = []
    for sc in scenarios:
        if assess_v1:
            label, fwd, wrist, rules = v1_assess(sc["landmarks"])
        else:
            a = detector.assess(sc["landmarks"])
            label, fwd, wrist, rules = a.label, a.forward_head_metric, a.wrist_deviation_metric, a.triggered_rules
        results.append(
            CaseResult(
                scenario_id=sc["id"],
                expected=sc["label"],
                predicted=label,
                forward_head_metric=fwd,
                wrist_deviation_metric=wrist,
                triggered_rules=list(rules),
                notes=sc.get("notes", ""),
            )
        )
    return results


def _banner(console: Console, text: str, style: str = "bold magenta") -> None:
    console.print()
    console.print(Panel(Text(text, style=style), border_style=style.split()[-1], expand=False))


def main() -> int:
    console = Console()
    benchmarks = json.loads(Path(BENCHMARKS_PATH).read_text())
    scenarios = benchmarks["scenarios"]

    _banner(console, "THE RSI LOOP — Narrated Demo")
    console.print(
        Panel(
            Text.assemble(
                ("Project: ", "bold"), ("The RSI Loop\n", "white"),
                ("Goal:    ", "bold"), ("Detect Repetitive Strain Injury risk from posture landmarks,\n", "white"),
                ("         ", "bold"), ("with the detector improving its own logic against a benchmark\n", "white"),
                ("         ", "bold"), ("suite, supervised by a regulatory Auditor.\n", "white"),
                ("Stages:  ", "bold"), ("(1) Accuracy on benchmarks   (2) Compliance with clinical norms.", "white"),
            ),
            border_style="magenta",
            expand=False,
        )
    )

    # -----------------------------------------------------------------------
    # Cycle 1 — v1 (intentionally flawed)
    # -----------------------------------------------------------------------
    _banner(console, "Cycle 1 — Running v1 (intentionally flawed) detector", style="bold red")
    console.print(
        "[dim]v1 uses signed horizontal offsets:  ear.x − shoulder.x > 0.15  and  hand_x − wrist_x > 0.10.[/]"
    )
    v1_results = _to_results(scenarios, assess_v1=True)
    v1_metrics = Metrics.from_results(v1_results)
    _render_log(console, v1_results, v1_metrics)

    # -----------------------------------------------------------------------
    # Self-correction narrative
    # -----------------------------------------------------------------------
    _banner(console, "Self-Improvement Cycle — Analysis & Proposed Fix", style="bold yellow")
    console.print(
        Panel(
            Text.assemble(
                ("Failure analysis:\n", "bold"),
                ("  S06 (radial deviation) was misclassified as Safe. The v1 wrist check\n", "white"),
                ("  uses a SIGNED offset (hand_x − wrist_x > 0.10) — it only fires when\n", "white"),
                ("  the hand is displaced toward +x. A wrist bent the other way produces\n", "white"),
                ("  a NEGATIVE offset and is silently ignored.\n\n", "white"),
                ("Proposed fix:\n", "bold"),
                ("  Replace both heuristics with proper trigonometric angles.\n", "white"),
                ("    • Forward-head:  atan2(|ear.x − shoulder.x|, |shoulder.y − ear.y|)\n", "cyan"),
                ("    • Wrist:         angle between forearm vector (elbow→wrist)\n", "cyan"),
                ("                     and metacarpal vector (wrist→hand_center).\n", "cyan"),
                ("  Both are direction-agnostic, so radial and ulnar bends are caught\n", "white"),
                ("  symmetrically. New thresholds: 20° (head) and 50° (wrist).\n\n", "white"),
                ("Result:  ", "bold"), ("v2 detector — already shipped in detector.py.", "green"),
            ),
            border_style="yellow",
            expand=False,
        )
    )

    # -----------------------------------------------------------------------
    # Cycle 2 — v2 (current detector.py)
    # -----------------------------------------------------------------------
    _banner(console, "Cycle 2 — Running v2 (corrected) detector", style="bold green")
    console.print(
        "[dim]v2 reads the live thresholds from detector.py — "
        f"forward-head {detector.FORWARD_HEAD_ANGLE_THRESHOLD_DEG}°, "
        f"wrist {detector.WRIST_DEVIATION_ANGLE_THRESHOLD_DEG}°.[/]"
    )
    v2_results = _to_results(scenarios, assess_v1=False)
    v2_metrics = Metrics.from_results(v2_results)
    _render_log(console, v2_results, v2_metrics)

    # -----------------------------------------------------------------------
    # Stage 2 — regulatory audit
    # -----------------------------------------------------------------------
    _banner(console, "Stage 2 — Regulatory Audit (anti-reward-hacking)", style="bold cyan")
    console.print(
        "[dim]The Auditor compares v2's thresholds against the Clinical Gold Standard. "
        "A loop that hacked thresholds into clinically implausible values would be rejected here.[/]"
    )
    audit_report = auditor.run_audit()
    auditor.render_report(audit_report, console=console)

    # -----------------------------------------------------------------------
    # Final status
    # -----------------------------------------------------------------------
    final_status, exit_code = _final_status(v2_metrics, audit_report)
    _render_final(console, final_status)

    console.print()
    console.print(
        Panel(
            Text.assemble(
                ("Demo complete. ", "bold"),
                ("Next steps:\n", "white"),
                ("  • Run ", "white"), ("python3 test_engine.py", "cyan"), (" for the unnarrated, machine-readable run.\n", "white"),
                ("  • Edit ", "white"), ("detector.py", "cyan"), (" thresholds and re-run to see Stage 2 catch reward hacking.\n", "white"),
                ("  • Add scenarios to ", "white"), ("benchmarks.json", "cyan"), (" to expand coverage.", "white"),
            ),
            border_style="magenta",
            expand=False,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
