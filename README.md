# The RSI Loop — A Validated Self-Improving Detector for Repetitive Strain Injury

**The RSI Loop** is a self-improving (Recursive Self-Improvement) computer-vision pipeline that detects ergonomic risks for Repetitive Strain Injury in computer users. It estimates **forward-head posture** and **wrist ulnar/radial deviation** from MediaPipe pose and hand landmarks, improves its own detection logic against a benchmark suite, and is supervised by a regulatory Auditor that keeps the self-evolved thresholds inside published clinical norms.

> Built for the [pharmatools.ai](https://pharmatools.ai) portfolio.

---

## Quick start

```bash
python3 -m pip install -r requirements.txt
python3 demo.py            # narrated v1 → v2 evolution + final audit (start here)
python3 test_engine.py     # unnarrated run, machine-readable output
python3 auditor.py         # Stage-2 audit only
```

---

## Why this project exists

Self-improving systems have a well-known failure mode: **specification gaming**, also known as **reward hacking**. If the only objective is "pass the test suite," a sufficiently flexible loop will mutate its parameters into values that satisfy the metric but destroy real-world meaning. A wrist-deviation threshold of 999° passes every benchmark — and is also useless on a real user.

The RSI Loop demonstrates a *Validated* form of self-improvement: a two-stage gate that lets the loop optimise freely, but only accepts iterations that are simultaneously **accurate** and **clinically plausible**.

---

## Two-Stage Validation

```
                    ┌──────────────────────────────────────┐
                    │        STAGE 1 — ACCURACY            │
                    │                                      │
benchmarks.json ───▶│  detector.assess(landmarks) for each │
                    │  labelled scenario in the suite.     │
                    │                                      │
                    │  Pass condition:                     │
                    │      accuracy ≥ 90 %                 │
                    └─────────────────┬────────────────────┘
                                      │  (gate)
                                      ▼
                    ┌──────────────────────────────────────┐
                    │        STAGE 2 — COMPLIANCE          │
                    │                                      │
detector thresholds │  Auditor compares each AI-tuned      │
       ───────────▶ │  threshold to the Clinical Gold      │
                    │  Standard.                           │
                    │                                      │
                    │  Pass condition:                     │
                    │      every finding == "PASS"         │
                    └─────────────────┬────────────────────┘
                                      │
                                      ▼
                       RSI LOOP STATUS: COMPLETE
```

### Stage 1 — Accuracy (Benchmarks)
`test_engine.py` runs `detector.assess` against every labelled scenario in `benchmarks.json` and computes precision, recall, F1 and accuracy. Anything under the 90 % accuracy gate exits with code `1` (`NOT_ACCURATE`) and the auditor is **not** invoked — there is no point auditing a model that does not work.

### Stage 2 — Compliance (Auditor)
Once Stage 1 passes, `auditor.run_audit()` reads each tunable constant out of `detector.py` (`getattr` against the live module) and matches it against the Clinical Gold Standard. Each threshold receives one of three statuses:

| Status | Trigger | Effect on the loop |
| --- | --- | --- |
| `PASS` | Threshold inside the clinical range | Stage 2 passes |
| `WARNING` | Inside the ±5° tolerance band but outside the clinical range | `NOT_COMPLIANT` |
| `HARD FAILURE` | Outside the tolerance band, ≤ 0, or non-finite | `NOT_COMPLIANT` (likely reward-hacked) |

The final RSI Loop status is `COMPLETE` only when Stage 1 *and* Stage 2 are clean.

### Clinical Gold Standard

Hard-coded in `auditor.py`:

| Threshold | Expected range | Tolerance band |
| --- | --- | --- |
| `FORWARD_HEAD_ANGLE_THRESHOLD_DEG` | **15.0° – 25.0°** | ±5° → warning, beyond → hard failure |
| `WRIST_DEVIATION_ANGLE_THRESHOLD_DEG` | **40.0° – 60.0°** | ±5° → warning, beyond → hard failure |

Both ranges follow ergonomic literature on craniovertebral angle and ulnar/radial wrist deviation.

---

## How this prevents Specification Gaming / Reward Hacking

A common pitfall in any AI loop with an internal optimiser is **reward hacking**: the system finds a way to maximise its own score without solving the underlying problem. In a threshold-tuning loop, that looks like:

| Attack | Stage 1 alone? | Stage 2 catches it? |
| --- | --- | --- |
| Set thresholds to absurd values (e.g. `wrist_threshold = 999°`) so nothing trips | ❌ — also misclassifies the High Strain scenarios | ✅ `HARD FAILURE` (way outside clinical range) |
| Set thresholds to `0.0` so everything trips | ❌ — also misclassifies the Safe scenarios | ✅ `HARD FAILURE` (non-positive) |
| Set thresholds to `NaN` / `inf` to short-circuit comparisons | depends on language semantics | ✅ `HARD FAILURE` (non-finite check) |
| **Plausible-but-wrong**: nudge `wrist_threshold` to `67°` to "smooth over" a noisy benchmark | ✅ passes 100% | ✅ `HARD FAILURE` (7° beyond clinical max) |
| Subtly drift `wrist_threshold` to `62°` | ✅ likely passes | ⚠️ `WARNING` — flagged for review, loop status `NOT_COMPLIANT` |

**The general principle: passing the test is necessary but not sufficient.** The thresholds must also look like something a clinician would write down. Stage 2 grounds the optimiser in domain knowledge that exists *outside* the benchmark suite, which is what makes the suite ungameable.

To verify the guard rail interactively, set `WRIST_DEVIATION_ANGLE_THRESHOLD_DEG = 67.0` in `detector.py` and re-run `python3 test_engine.py`. Stage 1 still passes 100% — but Stage 2 returns `HARD FAILURE` (67° is 7° beyond the clinical maximum, outside the ±5° tolerance band), the final status flips to `NOT_COMPLIANT`, and the iteration is rejected.

---

## Architecture

| File | Role |
| --- | --- |
| `detector.py` | Pure geometric classifier. Forward-head and wrist-deviation angles, with two tunable thresholds. Optional MediaPipe webcam pipeline (lazy-imported). |
| `benchmarks.json` | 10 labelled ground-truth scenarios — neutral typing, forward head, ulnar deviation, radial deviation, combined strain, borderline cases. |
| `auditor.py` | Loads thresholds from `detector.py`, compares them to the Clinical Gold Standard, emits a `PASS` / `WARNING` / `HARD FAILURE` compliance report. |
| `test_engine.py` | Two-stage harness: accuracy on benchmarks → audit → final status. Prints the rich Self-Improvement Log and persists `last_run.json`. |
| `demo.py` | Narrated single-run tour: replays the v1 → v2 evolution and the final audit. **Recommended entry point for reviewers.** |
| `requirements.txt` | `mediapipe`, `opencv-python`, `rich`, `pytest`. |
| `last_run.json` | Machine-readable summary of the most recent run, for diffing across iterations. |

---

## The Self-Improvement Cycle, captured

| Cycle | Detector | Forward-head check | Wrist check | Accuracy | Recall | Audit |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | v1 (intentionally flawed) | Signed `ear.x − shoulder.x > 0.15` | Signed one-sided `hand_x − wrist_x > 0.10` | 90 % | 80 % | not run (under gate) |
| 2 | v2 (current) | `atan2` angle off vertical, threshold **20°** | Vector angle between forearm and metacarpal axes, threshold **50°** | **100 %** | **100 %** | **PASS** |

Cycle 1 missed the radial-deviation scenario `S06` because v1's wrist check inspected only one side of the offset. The proposed fix replaced both crude offsets with proper trigonometric angles (direction-agnostic), and Cycle 2 reached `COMPLETE`.

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
python3 -c "from detector import assess_from_webcam; print(assess_from_webcam())"
```

The webcam pipeline is gated behind a lazy import, so the rest of the project runs without `mediapipe` or `opencv-python` installed.

---

## Extending the loop

- **Add benchmarks** by editing `benchmarks.json`. Each scenario needs the six landmarks the detector uses (`ear`, `shoulder`, `elbow`, `wrist`, `index_mcp`, `pinky_mcp`) plus a `Safe` / `High Strain` label.
- **Add ergonomic rules** by adding a new pure-function angle helper in `detector.py` plus its threshold constant; then add a matching entry to `CLINICAL_GOLD_STANDARD` in `auditor.py` so the new constant is regulated from day one.
- **Tighten the gold standard** if you have stronger clinical evidence — narrow the expected range and the loop is forced to converge on more conservative thresholds.
