"""Build the Zenodo deposit for RSI Loop 2: every trajectory artifact, the frozen analysis
output, a manifest with SHA-256 for every file, and a README. Nothing in the archive is
modified; the manifest lets anyone verify a trajectory against what was analysed.

    python3 -m experiments.make_archive [--out ~/Desktop/rsi-loop-2-archive]

Produces  <out>/rsi-loop-2-artifacts-<tag>.zip  and  <out>/SHA256SUMS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE = ["artifacts", "analysis/out", "experiments/preregistration.md",
           "docs/rsi-loop-2-research-design.md", "docs/rsi-loop-2-results.md", "env/manifests"]
RUNS = {"confirm-01": "primary: arms A–D × seeds 1000–1009, claude-sonnet-5, notes on (40)",
        "confirm-01-opus": "strong tier: arms B, D × seeds 1000–1009, claude-opus-5 (20)",
        "confirm-01-nonotes": "recursive channel off: arms B, D × seeds 1000–1009, claude-sonnet-5 (20)",
        "baseline-01": "parametric hill-climber: arms A–D × seeds 1000–1009 (40, no LLM)",
        "pilot-01": "pilot (pre-freeze; seeds 1–3): not used in any confirmatory analysis",
        "pilot-02": "pilot (pre-freeze; seeds 1–3): not used in any confirmatory analysis",
        "pilot-03": "pilot (pre-freeze; seeds 1–3): not used in any confirmatory analysis"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path.home() / "Desktop" / "rsi-loop-2-archive")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    commit, tag = git("rev-parse", "HEAD"), git("describe", "--tags", "--always")
    files = []
    for inc in INCLUDE:
        p = ROOT / inc
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files += [q for q in sorted(p.rglob("*")) if q.is_file() and "__pycache__" not in q.parts and q.name != ".DS_Store"]
    manifest = {"created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "git_commit": commit, "git_describe": tag,
                "freeze_tag": "v2.0-freeze", "runs": RUNS, "n_files": len(files),
                "files": {str(f.relative_to(ROOT)): {"sha256": sha256(f), "bytes": f.stat().st_size} for f in files}}
    traj = [f for f in files if f.name == "trajectory.json"]
    manifest["n_trajectories"] = len(traj)
    manifest["trajectories"] = {}
    for t in traj:
        d = json.loads(t.read_text())
        manifest["trajectories"][str(t.parent.relative_to(ROOT))] = {
            "status": d.get("status"), "generations": len(d.get("generations", [])),
            "model": d.get("config", {}).get("model"), "notes_enabled": d.get("config", {}).get("notes_enabled"),
            "cost_usd": round(d.get("totals", {}).get("cost_usd", 0.0), 4)}
    readme = f"""RSI Loop 2 — trajectory artifacts and frozen analysis output
=============================================================

Repository : https://github.com/nickjlamb/rsi-loop   (code is MIT-licensed; this archive is CC BY 4.0)
Freeze tag : v2.0-freeze (1 October 2026)     Archive built from commit {commit} ({tag})
Design     : docs/rsi-loop-2-research-design.md      Preregistration: experiments/preregistration.md
Results    : docs/rsi-loop-2-results.md              Analysis output: analysis/out/

Runs in artifacts/ (one folder per run id, then arm_<A-D>/seed_<nnnn>/):
""" + "".join(f"  {k:<20} {v}\n" for k, v in RUNS.items()) + f"""
Each trajectory folder holds trajectory.json (config, prompt hashes, dataset manifest hashes, every
generation's scores and gate decision) and gen_00 … gen_20, each with policy.py (the candidate),
notes.md (the optimiser's notes), diff.patch, call.json (the full prompt/response transcript, token
counts, cost), scores.json (visible, hidden, envelope, canary results and the decision),
events.jsonl (sandbox audit events) and timing.json. gen_00 is the shared starting policy.

Hidden quantities (the simulator rule, the hidden set H, balanced accuracy on H) were never shown to
the optimiser; they appear in scores.json because the harness computed them for the record. The
optimiser's own context is reproducible from call.json["transcript"].

Pilot runs (seeds 1–3) are included for completeness and were never reused in the confirmatory
analysis. Post-freeze harness and analysis defects are listed in experiments/preregistration.md §13.

MANIFEST.json lists SHA-256 and size for every file; SHA256SUMS (beside the zip) covers the zip.
{len(files)} files; {len(traj)} trajectories.
"""
    zpath = a.out / f"rsi-loop-2-artifacts-{tag}.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("rsi-loop-2/README.txt", readme)
        z.writestr("rsi-loop-2/MANIFEST.json", json.dumps(manifest, indent=1))
        for f in files:
            z.write(f, "rsi-loop-2/" + str(f.relative_to(ROOT)))
    (a.out / "SHA256SUMS").write_text(f"{sha256(zpath)}  {zpath.name}\n")
    (a.out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote {zpath} ({zpath.stat().st_size / 1e6:.1f} MB), {len(files)} files, {len(traj)} trajectories")
    print((a.out / "SHA256SUMS").read_text().strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
