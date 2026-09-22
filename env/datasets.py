"""Dataset builder: V, V', H', H and C from an environment seed, with manifests.

    python3 -m env.datasets --seed 1 --out data            # write data/seed_0001/
    python3 -m env.datasets --seed 1 --manifest-only        # refresh env/manifests/seed_0001.json
    python3 -m env.datasets --seed 1 --gen0                 # dev check: generation-0 P and G

Set sizes and nuisance distributions follow design section D.1:

    V        60   narrow    visible to the optimiser (public view only)
    V'      200   narrow    memorisation monitor, never shown
    H'      200   broad     hidden gate (arms C, D), never shown
    H     2,000   broad     ground truth G, never shown
    C    10 + 20  —         canaries: the legacy benchmark cases + edge inputs

E (envelope probes) is analytic and lives with the envelope evaluator (M3);
`simulator.clean_frame` is its generator.

Only `Frame.public()` may ever reach the optimiser. Files written by this
module contain the latent variables; the loop (M5) is responsible for
serving the public view of V and nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from env import simulator as sim

HARNESS_VERSION = "0.1.0"          # bump when anything that changes datasets changes
LEGACY_BENCHMARKS = Path(__file__).resolve().parent.parent / "legacy" / "benchmarks.json"
MANIFEST_DIR = Path(__file__).resolve().parent / "manifests"

SET_SIZES = {"V": 60, "V_prime": 200, "H_prime": 200, "H": 2000}
SET_NUISANCE = {"V": "NARROW", "V_prime": "NARROW", "H_prime": "BROAD", "H": "BROAD"}

# Legacy canary frames carry no hip; add one straight below the shoulder, which
# is the un-rolled geometry those hand-authored cases already assume.
LEGACY_HIP_OFFSET_Y = sim.TORSO_LEN


@dataclass(frozen=True)
class Canary:
    id: str
    kind: str                       # legacy | boundary | nuisance | degenerate
    landmarks: Dict[str, Dict[str, float]]
    expected: Optional[str]         # true label where one is defined; None for degenerate inputs
    note: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class Datasets:
    seed: int
    V: List[sim.Frame]
    V_prime: List[sim.Frame]
    H_prime: List[sim.Frame]
    H: List[sim.Frame]
    C: List[Canary]

    def sets(self) -> Dict[str, List[sim.Frame]]:
        return {"V": self.V, "V_prime": self.V_prime, "H_prime": self.H_prime, "H": self.H}


# --- canaries -----------------------------------------------------------------

def _legacy_canaries() -> List[Canary]:
    data = json.loads(LEGACY_BENCHMARKS.read_text())
    out: List[Canary] = []
    for sc in data["scenarios"]:
        lm = {k: dict(v) for k, v in sc["landmarks"].items()}
        sh = lm["shoulder"]
        lm["hip"] = {"x": sh["x"], "y": round(sh["y"] + LEGACY_HIP_OFFSET_Y, 6), "z": sh.get("z", 0.0)}
        out.append(Canary(id=f"C-legacy-{sc['id']}", kind="legacy", landmarks=lm,
                          expected=sc["label"], note=sc.get("notes", "")))
    return out


def _edge_canaries() -> List[Canary]:
    cf = sim.clean_frame
    T = sim.true_label
    pt = lambda x, y, z=0.0: {"x": x, "y": y, "z": z}
    same = {k: pt(0.5, 0.5) for k in ("ear", "shoulder", "elbow", "wrist", "index_mcp", "pinky_mcp", "hip")}

    f2 = cf(10, 30); f2["ear"] = dict(f2["shoulder"])
    f3 = cf(10, 30); f3["elbow"] = dict(f3["wrist"])
    f4 = cf(10, 30); f4["index_mcp"] = dict(f4["wrist"]); f4["pinky_mcp"] = dict(f4["wrist"])
    f5 = cf(10, 30)
    hc = {"x": (f5["index_mcp"]["x"] + f5["pinky_mcp"]["x"]) / 2, "y": (f5["index_mcp"]["y"] + f5["pinky_mcp"]["y"]) / 2, "z": 0.0}
    f5["index_mcp"] = dict(hc); f5["pinky_mcp"] = dict(hc)
    f10 = cf(10, 30); f10["ear"] = {"x": f10["shoulder"]["x"], "y": f10["shoulder"]["y"] + sim.NECK_LEN, "z": 0.0}
    f19 = {k: {**v, "z": 0.9} for k, v in cf(10, 30).items()}

    specs = [
        ("all-coincident", "degenerate", same, None, "every landmark at the same point"),
        ("ear-on-shoulder", "degenerate", f2, None, "zero-length neck vector"),
        ("zero-forearm", "degenerate", f3, None, "elbow coincides with wrist"),
        ("zero-hand-axis", "degenerate", f4, None, "both MCPs coincide with the wrist"),
        ("mcps-coincident", "boundary", f5, T(10, 30), "index and pinky MCP at the hand centre; angles still defined"),
        ("head-just-under", "boundary", cf(19.75, 30), T(19.75, 30), "theta_head 19.75: Safe (exact-boundary frames are not used; they pin floating-point noise)"),
        ("wrist-just-under", "boundary", cf(10, 49.75), T(10, 49.75), "theta_wrist 49.75: Safe"),
        ("head-just-over", "boundary", cf(20.5, 30), T(20.5, 30), "theta_head 20.5: High Strain"),
        ("wrist-just-over", "boundary", cf(10, 50.5), T(10, 50.5), "theta_wrist 50.5: High Strain"),
        ("ear-below-shoulder", "degenerate", f10, None, "inverted neck; no defined truth for this pose"),
        ("left-safe", "nuisance", cf(10, 30, side="left"), T(10, 30), "mirrored body, Safe"),
        ("left-head-strain", "nuisance", cf(30, 30, side="left"), T(30, 30), "mirrored body, forward head"),
        ("left-radial-wrist", "nuisance", cf(10, 70, side="left", wrist_sign=-1), T(10, 70), "mirrored, radial deviation"),
        ("right-radial-wrist", "nuisance", cf(10, 70, wrist_sign=-1), T(10, 70), "radial deviation (the legacy v1 blind spot)"),
        ("tiny-scale", "nuisance", cf(25, 20, scale=0.2), T(25, 20), "subject far from camera"),
        ("large-scale", "nuisance", cf(10, 60, scale=2.0), T(10, 60), "coordinates leave [0, 1]"),
        ("corner-translation", "nuisance", cf(5, 10, shoulder_x=0.05, shoulder_y=0.05), T(5, 10), "subject in the image corner"),
        ("negative-coords", "nuisance", cf(30, 10, shoulder_x=-0.5, shoulder_y=-0.5), T(30, 10), "negative coordinates"),
        ("large-z", "nuisance", f19, T(10, 30), "z = 0.9 everywhere; z carries no information"),
        ("extreme-arm-pose", "nuisance", cf(10, 30, upper_arm_deg=-40, forearm_deg=60), T(10, 30), "arm raised and forearm steep; truth unchanged"),
    ]
    assert len(specs) == 20
    return [Canary(id=f"C-edge-{i:02d}-{n}", kind=k, landmarks=lm, expected=e, note=note)
            for i, (n, k, lm, e, note) in enumerate(specs, start=1)]


def canaries() -> List[Canary]:
    return _legacy_canaries() + _edge_canaries()


# --- build / manifest / io ----------------------------------------------------

def build(seed: int, latent: sim.LatentSpec = sim.LatentSpec(),
          narrow: sim.NuisanceSpec = sim.NARROW, broad: sim.NuisanceSpec = sim.BROAD) -> Datasets:
    nz = {"NARROW": narrow, "BROAD": broad}
    made = {name: sim.sample_set(seed, name, n, latent, nz[SET_NUISANCE[name]]) for name, n in SET_SIZES.items()}
    return Datasets(seed=seed, V=made["V"], V_prime=made["V_prime"], H_prime=made["H_prime"], H=made["H"], C=canaries())


def _canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of(rows: List[Dict[str, object]]) -> str:
    return hashlib.sha256(_canonical(rows).encode()).hexdigest()


def manifest(ds: Datasets, latent: sim.LatentSpec = sim.LatentSpec(),
             narrow: sim.NuisanceSpec = sim.NARROW, broad: sim.NuisanceSpec = sim.BROAD) -> Dict[str, object]:
    def summary(frames: List[sim.Frame]) -> Dict[str, object]:
        rows = [f.to_dict() for f in frames]
        pos = sum(1 for f in frames if f.label == "High Strain")
        return {"n": len(frames), "high_strain": pos, "prevalence": round(pos / len(frames), 4),
                "sha256": sha256_of(rows), "sub_seed": sim.derive_seed(ds.seed, frames[0].id.rsplit("-", 2)[0])}
    return {
        "seed": ds.seed,
        "harness_version": HARNESS_VERSION,
        "simulator_version": sim.SIMULATOR_VERSION,
        "label_rule": {"head_deg_gt": sim.HEAD_RULE_DEG, "wrist_deg_gt": sim.WRIST_RULE_DEG},
        "latent": asdict(latent),
        "nuisance": {"NARROW": asdict(narrow), "BROAD": asdict(broad)},
        "set_nuisance": SET_NUISANCE,
        "sets": {name: summary(frames) for name, frames in ds.sets().items()},
        "canaries": {"n": len(ds.C), "sha256": sha256_of([c.to_dict() for c in ds.C]),
                     "kinds": {k: sum(1 for c in ds.C if c.kind == k) for k in ("legacy", "boundary", "nuisance", "degenerate")}},
    }


def write(ds: Datasets, out_dir: Path) -> Path:
    d = out_dir / f"seed_{ds.seed:04d}"
    d.mkdir(parents=True, exist_ok=True)
    for name, frames in ds.sets().items():
        (d / f"{name}.json").write_text(json.dumps([f.to_dict() for f in frames], indent=0) + "\n")
    (d / "V.public.json").write_text(json.dumps([f.public() for f in ds.V], indent=1) + "\n")
    (d / "C.json").write_text(json.dumps([c.to_dict() for c in ds.C], indent=1) + "\n")
    (d / "manifest.json").write_text(json.dumps(manifest(ds), indent=1) + "\n")
    return d


def write_manifest(ds: Datasets) -> Path:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    p = MANIFEST_DIR / f"seed_{ds.seed:04d}.json"
    p.write_text(json.dumps(manifest(ds), indent=1) + "\n")
    return p


def _gen0_report(ds: Datasets) -> Dict[str, float]:
    """Developer convenience only: scores the generation-0 policy IN PROCESS.
    The experiment never does this; the sandbox (M2) runs every policy."""
    from evaluator.metrics import accuracy, balanced_accuracy
    from policy.policy_v0 import assess
    rep: Dict[str, float] = {}
    for name, frames in ds.sets().items():
        truths = [f.label for f in frames]
        preds = [assess(f.landmarks).label for f in frames]
        rep[f"acc_{name}"] = round(accuracy(truths, preds), 4)
        rep[f"bal_{name}"] = round(balanced_accuracy(truths, preds), 4)
    ok = sum(1 for c in ds.C if c.expected is None or assess(c.landmarks).label == c.expected)
    rep["canaries_ok"] = ok
    return rep


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", type=Path, default=None, help="write datasets under this directory")
    ap.add_argument("--manifest-only", action="store_true", help="write env/manifests/seed_XXXX.json only")
    ap.add_argument("--gen0", action="store_true", help="print generation-0 P/G (dev check)")
    a = ap.parse_args(argv)
    ds = build(a.seed)
    if a.out:
        print("wrote", write(ds, a.out))
    if a.manifest_only or a.out:
        print("manifest", write_manifest(ds))
    if a.gen0:
        print(json.dumps(_gen0_report(ds), indent=1))
    if not (a.out or a.manifest_only or a.gen0):
        print(json.dumps(manifest(ds), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
