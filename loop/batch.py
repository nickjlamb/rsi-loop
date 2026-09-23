"""Run a set of trajectories unattended, re-invoking each one after an
infrastructure failure until it completes or runs out of attempts.

    python3 -m loop.batch --run-id pilot-02 --arms B D --seeds 1 --model anthropic/claude-sonnet-5
    python3 -m loop.batch --run-id pilot-02 --arms B D --seeds 1 2 3 --model ... --shuffle 7 --attempts 8

Each (arm, seed) pair is a call to loop.run.run_trajectory, which resumes from
its own artifacts, so a retry never repeats a paid, completed generation. A
halt caused by the cost guard is final for that trajectory. Order is the
given order, or a seeded shuffle (design D.6: interleaved across arms so that
provider drift is not confounded with arm). A batch.json log is written under
artifacts/<run-id>/ with every attempt, its outcome and cost.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from loop.config import ARTIFACTS_ROOT, RunConfig
from loop.run import run_trajectory


def plan(arms: Sequence[str], seeds: Sequence[int], shuffle_seed: Optional[int] = None) -> List[Tuple[str, int]]:
    pairs = [(a, s) for s in seeds for a in arms]
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(pairs)
    return pairs


def run_batch(run_id: str, pairs: Sequence[Tuple[str, int]], *, model: str, provider_factory=None, attempts: int = 6,
              pause_s: float = 60.0, artifacts_root: Path = ARTIFACTS_ROOT, mock: bool = False, quiet: bool = False,
              **cfg_kw) -> List[dict]:
    log_path = artifacts_root / run_id / "batch.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log: List[dict] = json.loads(log_path.read_text()) if log_path.exists() else []
    for arm, seed in pairs:
        cfg = RunConfig(run_id=run_id, arm=arm, seed=seed, model=model, provider="scripted" if mock else "perplexity-agent",
                        artifacts_root=artifacts_root, mock=mock, **cfg_kw)
        for attempt in range(1, attempts + 1):
            provider = provider_factory(cfg) if provider_factory else None
            t0 = time.time()
            st = run_trajectory(cfg, provider=provider, quiet=quiet)
            entry = {"arm": arm, "seed": seed, "attempt": attempt, "generations": len(st.summaries),
                     "cost_usd": round(st.cost_usd, 4), "halted": st.halted, "seconds": round(time.time() - t0, 1),
                     "at": time.time()}
            log.append(entry)
            log_path.write_text(json.dumps(log, indent=1) + "\n")
            done = len(st.summaries) >= cfg.generations
            if done or (st.halted and "cost guard" in st.halted):
                if not quiet:
                    print(f"[batch] {arm}/{seed}: {'complete' if done else 'stopped by cost guard'} after {attempt} attempt(s), ${st.cost_usd:.2f}")
                break
            if attempt < attempts:
                if not quiet:
                    print(f"[batch] {arm}/{seed}: infrastructure halt ({st.halted}); retrying in {pause_s:.0f}s ({attempt}/{attempts})")
                time.sleep(pause_s)
            elif not quiet:
                print(f"[batch] {arm}/{seed}: giving up after {attempts} attempts; re-run this batch later to resume")
    return log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--arms", nargs="+", required=True, choices=list("ABCD"))
    ap.add_argument("--seeds", nargs="+", type=int, required=True)
    ap.add_argument("--model", default="scripted")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--attempts", type=int, default=6)
    ap.add_argument("--pause", type=float, default=60.0)
    ap.add_argument("--shuffle", type=int, default=None, help="seed for an interleaved order; omit for the given order")
    ap.add_argument("--generations", type=int, default=20)
    ap.add_argument("--no-notes", action="store_true")
    ap.add_argument("--max-cost-usd", type=float, default=10.0)
    a = ap.parse_args(argv)
    pairs = plan(a.arms, a.seeds, a.shuffle)
    print("[batch] order:", " ".join(f"{x}/{s}" for x, s in pairs))
    log = run_batch(a.run_id, pairs, model=a.model if not a.mock else "scripted", attempts=a.attempts, pause_s=a.pause,
                    mock=a.mock, generations=a.generations, notes_enabled=not a.no_notes, max_cost_usd=a.max_cost_usd)
    total = sum(e["cost_usd"] for e in log)
    print(json.dumps({"trajectories": len(pairs), "attempts_logged": len(log), "total_cost_usd_this_log": round(total, 2)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
