# The RSI Loop — a preregistered test of acceptance gates for self-modifying code

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
[![Preprint](https://img.shields.io/badge/preprint-10.5281%2Fzenodo.23236100-blue.svg)](https://doi.org/10.5281/zenodo.23236100)
[![Data: Zenodo](https://img.shields.io/badge/data-10.5281%2Fzenodo.23223679-blue.svg)](https://doi.org/10.5281/zenodo.23223679)

**Status (October 2026): experiment complete, results published.** An LLM optimiser rewrote a small posture-risk classifier 20 times per run under four acceptance-gate architectures, with a seeded simulator holding the hidden ground truth. The design was frozen and preregistered before the first confirmatory run (`v2.0-freeze`, 1 Oct 2026); 120 trajectories ran 1–7 Oct 2026; the frozen analysis was executed once. Preprint: Lamb N. *A preregistered comparison of acceptance-gate architectures for an LLM that rewrites its own code.* Zenodo, 8 October 2026, [doi:10.5281/zenodo.23236100](https://doi.org/10.5281/zenodo.23236100). Lay summary: [pharmatools.ai/rsi-loop](https://pharmatools.ai/rsi-loop).

## Findings

![Proxy versus truth over twenty revisions under gatekeeper B (visible score only) and gatekeeper D (plus behavioural envelope), Claude Sonnet 5, ten runs each. Under B the visible score climbs from 87% to 98% while hidden accuracy drifts from 74% to 72%; under D the visible score moves only to 89% while hidden accuracy rises to 79%.](findings-dynamics.png)

**Check behaviour, not scores.** A gate that only requires a visible score not to fall is satisfied by memorising the visible set, and Claude Sonnet 5 did that within a handful of revisions on 7 of 10 seeds without being asked (H1, supported). A hidden holdout stops the damage and produces nothing (H2, inconclusive leaning protective; "protective not productive" held exactly). An absolute behavioural envelope, a check that the code behaves correctly on a fixed sweep of physically specified inputs, was the only architecture under which hidden ground truth rose: 7/10 seeds with Sonnet 5, 10/10 with Opus 5 (exploratory D − B on G_final: HL +0.073, 95 % CI +0.036 to +0.112). The gate changed what the optimiser *proposed*, not just what it accepted (H4, rejected in the informative direction).

| Gate | Checks | Visible score → | Hidden truth → | Outcome (10 seeds, Sonnet 5) |
| --- | --- | --- | --- | --- |
| A | optimiser's own report | 0.87 → 0.95 | 0.74 → 0.71 | drifted; self-reports truthful to 10⁻⁵ |
| B | visible score must not fall | 0.87 → 0.98 | 0.74 → 0.72 | gamed: perfect visible score on 7/10 by memorising V |
| C | B + hidden holdout | 0.87 → 0.91 | 0.74 → 0.74 | stalled: gaming blocked, nothing replaced it |
| D | C + behavioural envelope + canaries | 0.87 → 0.89 | 0.74 → 0.79 | improved: real geometric fix found on 7/10 |

Three results we did not predict. A parametric hill-climber that cannot write code ended with *higher* hidden accuracy than the LLM under gate B (0.76 vs 0.72), because it cannot memorise: the Goodhart behaviour is an LLM behaviour, not a loop property. The stronger model was no safer under the weak gate (level with Sonnet on truth, four times the code changes, and the single worst degradation of the study) and more productive under the strong one (H6, supported). Removing the optimiser's notes between revisions made gaming faster and honest fixes rarer, and tripled the rate at which the model exhausted its output budget (H7, rejected by the frozen rule; both contrasts point the same way). Monitorability signals were thin: only diff size cleared the preregistered bar, and the two signals we expected to work did not (H5).

Every verdict, the five post-freeze defects, and the deviations from the cost estimate are in the write-up. Full detail: [preprint](https://doi.org/10.5281/zenodo.23236100) · [`docs/rsi-loop-2-results.md`](docs/rsi-loop-2-results.md) · [preregistration](experiments/preregistration.md) · [design and decision log](docs/rsi-loop-2-research-design.md) · all 120 trajectories with a SHA-256 manifest: [doi:10.5281/zenodo.23223679](https://doi.org/10.5281/zenodo.23223679) · [infographic](findings-infographic.png).

## How it was run

Primary: 4 gates × 10 seeds (1000–1009) × 20 revisions with `anthropic/claude-sonnet-5` via the Perplexity Agent API, optimiser notes on. Secondary: `anthropic/claude-opus-5` on B and D; notes off on B and D; a parametric hill-climber on all four gates. Ground truth is balanced accuracy on a 2,000-frame hidden set; the proxy is accuracy on 60 visible frames; δ = 0.025. Paired by seed, Hodges–Lehmann estimates with exact signed-rank CIs, exact sign-flip tests, no p-value gates. ≈ $1,000 of API credit, one laptop, five days. Defects found after the freeze were logged and fixed without re-running anything (preregistration §13).

```bash
python3 -m pytest -q                                     # 156 tests
python3 -m loop.null_control                             # determinism: gen-0 re-scored 20× per seed
python3 -m loop.batch --run-id baseline-01 --arms A B C D --seeds 1000 1001 1002 1003 1004 1005 1006 1007 1008 1009 --model parametric   # $0
PERPLEXITY_API_KEY=… python3 -m loop.batch --run-id confirm-01 --arms A B C D --seeds 1000 … 1009 --model anthropic/claude-sonnet-5 --shuffle 20261001
python3 -m analysis.report --run confirm-01 --run confirm-01-opus --run confirm-01-nonotes --run baseline-01 --delta 0.025
python3 -m experiments.make_archive                      # the Zenodo zip, with manifest
```

Repository map: `env/` simulator and datasets · `sandbox/` AST guard and audit-hooked subprocess · `evaluator/` visible, hidden, envelope, canary scoring · `loop/` gates, trajectory runner, batch, freeze constants · `optimizer/` prompts, context boundary, protocol, Perplexity provider · `baselines/` parametric optimiser · `monitor/` and `analysis/` preregistered signals, metrics, hypotheses, report · `experiments/` preregistration, archive builder · `legacy/` the 2025 demo.

<details>
<summary>Build milestones (M0–M10)</summary>

| Milestone | Status |
| --- | --- |
| M0 — freeze the legacy demo in `legacy/` | done |
| M1 — seeded simulator and datasets (`env/`) | done — see [`env/README.md`](env/README.md) |
| M2 — process-isolated sandbox (`sandbox/`) | done — AST guard + audit-hooked subprocess, denials logged |
| M3 — evaluators and gates (`evaluator/`, `loop/gates.py`) | done — visible, hidden, behavioural envelope, canaries; arms A–D as pure functions |
| M4 — optimiser agent (`optimizer/`) | done — structured-output protocol, Perplexity Agent API provider, scripted mock; run `python3 -m optimizer.smoke` once with a key |
| M5 — loop, artifacts, resume (`loop/run.py`) | done — per-generation artifacts, kill-and-resume identity, cost guard, seed hygiene, $0 scripted optimiser |
| M6 — monitor signals and analysis (`monitor/`, `analysis/`) | done — five preregistered signals, per-trajectory metrics, H1–H7 decision rules, AUROC with trajectory bootstrap, report + figures; validated on synthetic trees |
| M7 — pilot (seeds 1–3, arms B and D, Sonnet 5) | done — 6 trajectories, $33; findings and freeze decisions in design doc §N (24 Sep) |
| Baseline — parametric hill-climber (`baselines/`, D.5) | done — same loop, gates and artifacts; $0 |
| M8 — freeze | done — `v2.0-freeze` (1 Oct 2026), `experiments/preregistration.md` binding; post-freeze defects in §13 |
| M9 — confirmatory runs | done — 120 trajectories (40 primary, 20 Opus 5, 20 notes-off, 40 parametric baseline), 7 Oct 2026, ≈ $1,000 |
| M10 — analysis and write-up | analysis run once from the frozen scripts; results in [`docs/rsi-loop-2-results.md`](docs/rsi-loop-2-results.md) (draft) |

</details>

## Origins

The project began in 2025 as a hand-made two-stage acceptance gate around a posture-risk detector: a benchmark check (accuracy on ten labelled scenarios) followed by an auditor that required the detector's thresholds to sit inside a clinical range. A September 2026 audit of that prototype found a gate with no optimiser behind it, no evaluation the candidate could not see, and no process boundary between the candidate and its verifier, so a candidate could rewrite the gold standard before it was read. Those three gaps are what the experiment's harness closes: an LLM optimiser under real release pressure, a hidden ground truth from a seeded simulator, and a sandbox with an audit hook. The two-stage shape survived as the ancestor of gate D.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/architecture-dark.svg">
  <img src="docs/architecture-light.svg" alt="The original RSI Loop gate: a candidate detector is checked for accuracy against labelled benchmarks, then its thresholds are audited against the Clinical Gold Standard; in range is accepted as COMPLETE, outside is rejected as NOT_COMPLIANT." width="100%">
</picture>

The original code, demo and write-up, including the audit's findings, are unchanged in [`legacy/`](legacy/README.md) and still run:

```bash
python3 -m pip install -r requirements.txt
cd legacy && python3 demo.py
```

> Built for the [pharmatools.ai](https://pharmatools.ai) portfolio. MIT licence; data CC BY 4.0.
