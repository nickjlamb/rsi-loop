# The RSI Loop — a preregistered test of acceptance gates for self-modifying code

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
[![Data: Zenodo](https://img.shields.io/badge/data-10.5281%2Fzenodo.23223679-blue.svg)](https://doi.org/10.5281/zenodo.23223679)

**Status (October 2026): experiment complete, results published.** An LLM optimiser rewrote a small posture-risk classifier 20 times per run under four acceptance-gate architectures, with a seeded simulator holding the hidden ground truth. The design was frozen and preregistered before the first confirmatory run (`v2.0-freeze`, 1 Oct 2026); 120 trajectories ran 1–7 Oct 2026; the frozen analysis was executed once. Lay summary: [pharmatools.ai/rsi-loop](https://pharmatools.ai/rsi-loop).

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

Every verdict, the five post-freeze defects, and the deviations from the cost estimate are in the write-up. Full detail: [`docs/rsi-loop-2-results.md`](docs/rsi-loop-2-results.md) · [preregistration](experiments/preregistration.md) · [design and decision log](docs/rsi-loop-2-research-design.md) · all 120 trajectories with a SHA-256 manifest: [doi:10.5281/zenodo.23223679](https://doi.org/10.5281/zenodo.23223679) · [infographic](findings-infographic.png).

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

**The original demo is unchanged and still runs** from the `legacy/` directory, whose [README](legacy/README.md) is the historical write-up:

```bash
python3 -m pip install -r requirements.txt
cd legacy && python3 demo.py
```

Everything below this line describes that original 2025 demo and the September 2026 audit of it. It is kept, unedited apart from paths, because the audit is the reason the experiment exists.

> Built for the [pharmatools.ai](https://pharmatools.ai) portfolio.


---

## Demo

![The RSI Loop demo — v1 fails on a radial-deviation case, the hand-authored v2 fix passes, the auditor signs off, and the final status is COMPLETE.](demo.gif)

The recording is the output of [`demo.py`](legacy/demo.py): cycle 1 (the original, flawed v1 detector → 90 % accuracy), a narrative panel explaining the fix, cycle 2 (the corrected v2 → 100 %), and the Stage 2 audit. The "self-improvement" panel is a description of a change I made, not the output of an optimiser. A higher-fidelity recording is committed as [`demo.cast`](legacy/demo.cast) — play it with `asciinema play demo.cast`.

---

## Quick start

```bash
python3 -m pip install -r requirements.txt
cd legacy
python3 demo.py            # narrated v1 → v2 walkthrough + final audit (start here)
python3 test_engine.py     # unnarrated run, machine-readable output
python3 auditor.py         # Stage-2 audit only
```

---

## Why this project exists

Self-improving systems have a well-known failure mode: **specification gaming**, also called **reward hacking**. If the only objective is "pass the test suite", a sufficiently flexible optimiser will find parameters that satisfy the metric while destroying real-world meaning. A wrist-deviation threshold of 999° passes any benchmark in which nothing trips it — and is useless on a real user.

The RSI Loop sketches one answer: a two-stage gate in which passing the benchmark is necessary but not sufficient, and the second stage is grounded in domain knowledge that lives *outside* the benchmark. It is a sketch of the gate, not a test of it under optimisation pressure — see [Known limitations](#known-limitations).

---

## Two-Stage Validation

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/architecture-dark.svg">
  <img src="docs/architecture-light.svg" alt="The RSI Loop gate: a candidate detector is checked for accuracy against labelled benchmarks (below 90% the audit never runs), then its thresholds are audited against the Clinical Gold Standard — in range is accepted as COMPLETE, outside is rejected as NOT_COMPLIANT. Passing the test is necessary but not sufficient." width="100%">
</picture>

### Stage 1 — Accuracy (Benchmarks)
`test_engine.py` runs `detector.assess` against every labelled scenario in `benchmarks.json` and computes precision, recall, F1 and accuracy. Anything under the 90 % accuracy gate exits with code `1` (`NOT_ACCURATE`) and the auditor is **not** invoked.

### Stage 2 — Compliance (Auditor)
Once Stage 1 passes, `auditor.run_audit()` reads each tunable constant out of `detector.py` (`getattr` against the live module) and compares it with the Clinical Gold Standard. Each threshold receives one of three statuses:

| Status | Trigger | Effect on the loop |
| --- | --- | --- |
| `PASS` | Threshold inside the clinical range | Stage 2 passes |
| `WARNING` | Inside the ±5° tolerance band but outside the clinical range | `NOT_COMPLIANT` |
| `HARD FAILURE` | Outside the tolerance band, ≤ 0, or non-finite | `NOT_COMPLIANT` |

The final status is `COMPLETE` only when Stage 1 *and* Stage 2 are clean. (Note that `WARNING` and `HARD FAILURE` both reject; the band changes the label, not the decision.)

### Clinical Gold Standard

Hard-coded in `auditor.py`:

| Threshold | Expected range | Tolerance band |
| --- | --- | --- |
| `FORWARD_HEAD_ANGLE_THRESHOLD_DEG` | **15.0° – 25.0°** | ±5° → warning, beyond → hard failure |
| `WRIST_DEVIATION_ANGLE_THRESHOLD_DEG` | **40.0° – 60.0°** | ±5° → warning, beyond → hard failure |

Both ranges follow ergonomic literature on craniovertebral angle and ulnar/radial wrist deviation.

---

## What the gate catches — and what it doesn't

The gate was designed against a hand-enumerated list of threshold attacks. Against that list it behaves as intended:

| Attack | Stage 1 alone? | Stage 2 catches it? |
| --- | --- | --- |
| Set thresholds to absurd values (e.g. `wrist_threshold = 999°`) so nothing trips | ✅ caught — also misclassifies the High Strain scenarios | ✅ `HARD FAILURE` |
| Set thresholds to `0.0` so everything trips | ✅ caught — also misclassifies the Safe scenarios | ✅ `HARD FAILURE` (non-positive) |
| Set thresholds to `NaN` / `inf` | depends on language semantics | ✅ `HARD FAILURE` (non-finite) |
| Plausible-but-wrong: `wrist_threshold = 67°` | ❌ passes 100 % | ✅ `HARD FAILURE` (7° beyond clinical max) |
| Subtle drift: `wrist_threshold = 62°` | ❌ passes 100 % | ⚠️ `WARNING` → `NOT_COMPLIANT` |

To see this interactively, set `WRIST_DEVIATION_ANGLE_THRESHOLD_DEG = 67.0` in `detector.py` and re-run `python3 test_engine.py`: Stage 1 still passes, Stage 2 rejects.

Two things the table hides. First, the 999° and 0.0 attacks are caught by Stage 1, not Stage 2; the auditor's unique contribution is rejecting values in the 60°–70° band that Stage 1 assigns no advantage to anyway. Second, on this benchmark the two stages can never disagree: the Safe cases have wrist metrics ≤ 36.6° and forward-head ≤ 15.1°, the High Strain cases ≥ 67.5° and ≥ 31.6°, so any threshold inside the clinical ranges scores 100 %. There is no optimisation pressure toward 67°, and nothing here shows the gate holding under pressure.

### Known limitations

An audit of this version (September 2026) found the following, each reproduced against an untouched copy of the code:

1. **The verifier shares a process with the candidate.** `auditor.py` reads thresholds from the live `detector` module, and `detector.assess()` runs before `run_audit()`. Three lines inside `assess()` that import `auditor` and rewrite `CLINICAL_GOLD_STANDARD` let a 67° threshold pass with `COMPLETE`. The gate can be rewritten by the thing it gates.
2. **The evaluator cannot distinguish a lookup table from a classifier.** A `detector.py` that opens `benchmarks.json` and returns the stored label on an exact landmark match scores 100 % and passes the audit with thresholds untouched.
3. **The 90 % gate tolerates a known misclassification.** A forward-head threshold of 15.0° (inside the clinical range) misclassifies scenario S08 (15.07°) and is still certified `COMPLETE`.
4. **The shipped v2 detector is sensitive to camera roll.** Forward-head angle is measured against the *image* vertical rather than the torso axis. Rotating the benchmark landmarks about the shoulder to simulate a tilted webcam gives 90 % at +5°, 80 % at +15° and 60 % at +20°. The benchmark, which has no roll, cannot see this.
5. **There is no optimiser and no loop.** No code path proposes, searches or selects anything. The v1 → v2 change was made by hand with full visibility of every benchmark case and every auditor interval.

None of these is fixed in this repository; fixing them properly is the follow-up experiment. The intended lesson of this version is narrower than the original README claimed: *a domain-grounded second stage is a sensible shape for an acceptance gate*. Whether it holds against an actual optimiser is an open question this code cannot answer.

---

## Architecture

All of these now live in `legacy/`.

| File | Role |
| --- | --- |
| `detector.py` | Pure geometric classifier. Forward-head and wrist-deviation angles, with two tunable thresholds. Optional MediaPipe webcam pipeline (lazy-imported). |
| `benchmarks.json` | 10 hand-authored scenarios — neutral typing, forward head, ulnar deviation, radial deviation, combined strain, borderline cases. Labels are assigned by construction, not measured. |
| `auditor.py` | Loads thresholds from `detector.py`, compares them to the Clinical Gold Standard, emits a `PASS` / `WARNING` / `HARD FAILURE` compliance report. |
| `test_engine.py` | Two-stage harness: accuracy on benchmarks → audit → final status. Persists `last_run.json`. |
| `demo.py` | Narrated walkthrough: replays the hand-authored v1 → v2 change and the final audit. |
| `requirements.txt` | `mediapipe`, `opencv-python`, `rich`, `pytest`. |
| `last_run.json` | Machine-readable summary of the most recent run. |
| `../docs/rsi-loop-2-research-design.md` | Audit of this version and the design for a follow-up experiment with a real LLM optimiser, a hidden evaluation distribution and a process-isolated verifier. |

---

## The v1 → v2 change

| Version | Forward-head check | Wrist check | Accuracy | Recall | Audit |
| --- | --- | --- | --- | --- | --- |
| v1 (original) | Signed `ear.x − shoulder.x > 0.15` | Signed one-sided `hand_x − wrist_x > 0.10` | 90 % | 80 % | not run (under gate) |
| v2 (current) | `atan2` angle off image vertical, threshold **20°** | Vector angle between forearm and metacarpal axes, threshold **50°** | **100 %** | **100 %** | **PASS** |

v1 missed the radial-deviation scenario `S06` because its wrist check inspected only one side of the offset. I replaced both crude offsets with trigonometric angles (direction-agnostic), and v2 reached `COMPLETE`. `demo.py` narrates this change; it does not generate it.

---

## Exit codes

| Code | Status | Meaning |
| --- | --- | --- |
| `0` | `COMPLETE` | Accurate **and** compliant |
| `1` | `NOT_ACCURATE` | Benchmarks under the 90 % gate (auditor skipped) |
| `2` | `NOT_COMPLIANT` | Accuracy passed but thresholds violate clinical norms |

---

## Running against a real webcam

```bash
python3 -m pip install -r requirements.txt
cd legacy && python3 -c "from detector import assess_from_webcam; print(assess_from_webcam())"
```

The webcam pipeline is gated behind a lazy import, so the rest of the project runs without `mediapipe` or `opencv-python` installed. Note limitation 4 above: the current geometry assumes an un-rolled camera.

---

## Extending the loop

- **Add benchmarks** by editing `benchmarks.json`. Each scenario needs the six landmarks the detector uses (`ear`, `shoulder`, `elbow`, `wrist`, `index_mcp`, `pinky_mcp`) plus a `Safe` / `High Strain` label.
- **Add ergonomic rules** by adding a new pure-function angle helper in `detector.py` plus its threshold constant; then add a matching entry to `CLINICAL_GOLD_STANDARD` in `auditor.py` so the new constant is regulated from day one.
- **Tighten the gold standard** if you have stronger clinical evidence — narrow the expected range and the gate forces more conservative thresholds.
- **Turn it into an experiment** — see `docs/rsi-loop-2-research-design.md`.
