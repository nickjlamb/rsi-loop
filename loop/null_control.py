"""Null control (design D.5): the generation-0 policy scored 20 times per seed.
Everything is deterministic, so every bundle must be identical; a difference is
an infrastructure regression.

    python3 -m loop.null_control --seeds 1000 1001 ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from env import datasets as dsm
from evaluator.bundle import score_candidate
from loop import freeze

ROOT = Path(__file__).resolve().parent.parent


def run(seed: int, repeats: int = 20) -> dict:
    freeze.check_seed(seed)
    ds = dsm.build(seed)
    src = (ROOT / "policy" / "policy_v0.py").read_text()
    bundles = [score_candidate(src, ds) for _ in range(repeats)]
    keys = [json.dumps({k: v for k, v in b.to_dict().items() if k not in ("elapsed_s", "denied_events")}, sort_keys=True) for b in bundles]
    return {"seed": seed, "repeats": repeats, "identical": len(set(keys)) == 1, "P_V": bundles[0].P_V, "G": bundles[0].G}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", nargs="+", type=int, required=True)
    ap.add_argument("--repeats", type=int, default=20)
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts" / "null-control.json")
    a = ap.parse_args(argv)
    res = [run(s, a.repeats) for s in a.seeds]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0 if all(r["identical"] for r in res) else 1


if __name__ == "__main__":
    sys.exit(main())
