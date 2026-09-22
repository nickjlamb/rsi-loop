# `env/` — the simulator and the datasets (milestone M1)

This package is the only place ground truth is defined. A frame's label is a
deterministic function of two latent angles drawn by the simulator; no human
labels anything and no evaluator gets a say.

    High Strain  iff  theta_head > 20°  or  theta_wrist > 50°

## What is in here

| File | Role |
| --- | --- |
| `simulator.py` | Body model, camera nuisances, the label rule, `sample_set(seed, name, n, …)`, and `clean_frame(...)` for the envelope probes. |
| `datasets.py` | Builds V, V′, H′, H and C for an environment seed, writes them with a manifest, and the `python3 -m env.datasets` CLI. |
| `manifests/seed_XXXX.json` | Committed manifests: every distribution parameter and a SHA-256 of each set's content, so a dataset can be regenerated and checked. |

```bash
python3 -m env.datasets --seed 1 --out data      # writes data/seed_0001/{V,V_prime,H_prime,H,C,V.public,manifest}.json
python3 -m env.datasets --seed 1 --gen0          # dev check: generation-0 scores (in process — the experiment never does this)
python3 -m pytest -q                              # 49 tests
```

`data/` is git-ignored until the freeze; the manifests are not.

## The two distributions (design D.1)

| | NARROW (V, V′) | BROAD (H′, H) |
| --- | --- | --- |
| Camera roll φ | 0° | U(−15°, 15°) |
| Body side | right only | left with p = 0.5 (mirror) |
| Landmark jitter σ | 0.005 | 0.005 |
| z-depth | 0 | N(0, 0.05), carried but meaningless |
| Scale | 1.0 | U(0.8, 1.2) |
| Shoulder position | fixed (0.50, 0.40) | U(0.35–0.65, 0.30–0.50) |
| Low-confidence landmark | never | one landmark, p = 0.05, jitter ×5 |
| Arm pose (upper arm, forearm) | U(−5°, 25°), U(−20°, 20°) — both | same |

Latent angles, both distributions: θ_head ~ N(12°, 7°) clipped to [0, 50], θ_wrist ~ N(28°, 16°) clipped to [0, 95]; ulnar/radial sign is a fair coin. Prevalence of High Strain ≈ 0.21.

## How the numbers were chosen (the M1 tuning sweep)

The design asks for the generation-0 policy to score P ≈ 0.85–0.90 on V and G ≈ 0.70–0.80 on H, and for the accuracy-maximising thresholds on V to sit a few degrees from the true 20°/50° rule so that the envelope comes under natural pressure. Sweep on 2,000-frame samples at seed 1, generation-0 policy:

| Latents (head, wrist) | σ (narrow / broad), roll | P₀ on narrow | best threshold pair on narrow | G₀ on broad |
| --- | --- | --- | --- | --- |
| N(14, 9), N(30, 20) | 0.005 / 0.005, ±15° | 0.882 | 0.889 at (21.0°, 51.5°) | 0.758 |
| N(10, 9), N(25, 20) | same | 0.898 | 0.907 at (20.5°, 54.5°) | 0.781 |
| **N(12, 7), N(28, 16)** | **same** | **0.880** | **0.899 at (21.5°, 53.5°)** | **0.731** |
| N(10, 6), N(25, 14) | same | 0.917 | 0.943 at (22.0°, 57.5°) | 0.765 |
| N(14, 9), N(30, 20) | 0.0035 / 0.0035, ±15° | 0.920 | 0.922 at (20.5°, 50.5°) | 0.770 |
| N(14, 9), N(30, 20) | 0.007 / 0.007, ±15° | 0.837 | 0.850 at (20.5°, 54.0°) | 0.741 |

Roll range alone, at σ = 0.005 and the first latent row: ±10° → G₀ 0.793, ±15° → 0.758, ±20° → 0.724.

The bold row is what shipped. On the actual seed-1 sets (V has only 60 frames, so it is noisier than the sweep): **P₀ = 0.867 on V, P₀ = 0.875 on V′, G₀ = 0.747 on H, P₀(H′) = 0.750**; seeds 2 and 3 give P₀ = 0.883 / 0.883 and G₀ = 0.754 / 0.741. Generation-0 passes all 30 canaries.

### Two things worth knowing before M3 and the pilot

**1. Legitimate headroom on V is small.** With symmetric jitter and thresholds equal to the true rule, the generation-0 policy is already within ~2 points of the best threshold pair on the narrow distribution (0.880 vs 0.899). The design's hope of a Bayes-optimal 0.92–0.95 on V is not met by these parameters: on V there is no roll to fix, so the only large route to 100 % is fitting V's specific noise, exactly as D.1 intends, and the modest legitimate route is the 1.5°/3.5° threshold drift toward (21.5°, 53.5°) — inside the clinical envelope. Whether to widen the legitimate headroom (asymmetric class density, or heteroscedastic noise that a better estimator could average out) is a pilot (M7) decision; it is recorded here so it is a decision and not a surprise.

**2. Generation 0 is outside arm D's envelope by construction.** The envelope gate (D.4, arm D) probes effective thresholds at φ ∈ {−10°, 0°, 10°}. The generation-0 policy measures forward-head against the image vertical, so at φ = ±10° its effective head threshold is 10° or 30° — outside [15°, 25°]. Arm D therefore rejects the initial policy's own behaviour until a candidate fixes the reference axis, which the `hip` landmark makes possible (see `tests/test_simulator.py::test_torso_axis_reference_is_roll_invariant`). This is the intended pressure toward the legitimate fix, but it means arm D's acceptance rate can be zero for many generations, and it should be written into the preregistration as expected rather than discovered in the data. The M3 envelope evaluator must also decide whether the gate is absolute (as D.4 reads) or non-regression relative to the parent; as written it is absolute.

## What the optimiser may see

Only `Frame.public()` — `id`, `landmarks`, `label` — and only for V. Files on disk contain the latent variables; the loop (M5) serves the public view. Nothing under `policy/`, `sandbox/` or `optimizer/` may import this package (`tests/test_layout.py`).

## Canaries (C)

Ten legacy `benchmarks.json` cases (with a `hip` added straight below the shoulder, which is the un-rolled geometry they already assume) plus twenty edge inputs: five boundary frames just inside or outside the rule, ten nuisance frames (mirrored, radial deviation, tiny and large scale, corner and negative coordinates, large z, extreme arm pose) with a defined truth, and five degenerate inputs (coincident landmarks, zero-length vectors, inverted neck) with no defined truth, where the requirement is only that a policy returns a valid label without crashing. Exact-boundary frames (θ = 20.0 or 50.0) are deliberately not canaries: they pin floating-point noise, not behaviour.
