"""Run a candidate policy in a fresh, isolated interpreter and return what
happened — every denial, error and timing — as data.

    result = run(source, frames)          # frames: list of landmark dicts, NO labels
    result.valid                          # guard clean, loaded, deterministic, no timeout
    result.predictions                    # list[str | None], aligned with frames
    result.denied_events                  # what the candidate tried and was refused

Validity is a sandbox property, not a quality judgement: a valid policy can be
wrong on every frame. Rejection reasons are categorical so that gates can pass
them to the optimiser without leaking anything else (design D.3).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from sandbox import ast_guard

CHILD = Path(__file__).resolve().parent / "_child.py"
CONTRACT_SRC = Path(__file__).resolve().parent.parent / "policy" / "contract.py"

DEFAULT_TIMEOUT_S = 60.0
DEFAULT_MEMORY_MB = 512
REASONS = ("ast_guard", "load_error", "timeout", "nondeterministic", "harness_error")


@dataclass
class SandboxResult:
    valid: bool
    reason: Optional[str]                       # one of REASONS, or None when valid
    predictions: List[Optional[str]]
    metrics: List[List[Optional[float]]]
    guard: Dict[str, object]
    denied_events: List[Dict[str, object]] = field(default_factory=list)
    logged_events: List[Dict[str, object]] = field(default_factory=list)
    frame_errors: int = 0
    error_samples: List[Dict[str, object]] = field(default_factory=list)
    load_error: Optional[str] = None
    deterministic: Optional[bool] = None
    runs: int = 0
    elapsed_s: float = 0.0
    child_stdout: str = ""
    child_stderr: str = ""

    @property
    def n(self) -> int:
        return len(self.predictions)

    def to_dict(self) -> Dict[str, object]:
        d = self.__dict__.copy()
        d["denied_event_count"] = len(self.denied_events)
        return d


def _write_workdir(source: str, frames: Sequence[Dict[str, Dict[str, float]]]) -> str:
    wd = tempfile.mkdtemp(prefix="rsi-sandbox-")
    Path(wd, "candidate.py").write_text(source)
    Path(wd, "frames.json").write_text(json.dumps(list(frames)))
    Path(wd, "contract.py").write_text(CONTRACT_SRC.read_text())
    Path(wd, "policy").mkdir()
    Path(wd, "policy", "__init__.py").write_text("")
    Path(wd, "policy", "contract.py").write_text(CONTRACT_SRC.read_text())
    return wd


def _run_child(wd: str, timeout_s: float, memory_mb: int) -> Dict[str, object]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    t0 = time.time()
    try:
        proc = subprocess.run([sys.executable, "-I", str(CHILD), wd, str(memory_mb)],
                              cwd=wd, env=env, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        return {"timeout": True, "elapsed_s": time.time() - t0,
                "stdout": (e.stdout or "")[-2000:] if isinstance(e.stdout, str) else "",
                "stderr": (e.stderr or "")[-2000:] if isinstance(e.stderr, str) else ""}
    res_path = Path(wd, "results.json")
    if not res_path.exists():
        return {"harness_error": f"child exited {proc.returncode} without results",
                "elapsed_s": time.time() - t0, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]}
    data = json.loads(res_path.read_text())
    data.update({"timeout": False, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:],
                 "returncode": proc.returncode, "wall_s": time.time() - t0})
    return data


def run(source: str, frames: Sequence[Dict[str, Dict[str, float]]], *, guard: bool = True,
        determinism_check: bool = True, timeout_s: float = DEFAULT_TIMEOUT_S,
        memory_mb: int = DEFAULT_MEMORY_MB, keep_workdir: bool = False) -> SandboxResult:
    """Execute `source` on `frames`. `guard=False` exists only so tests can
    prove the runtime layer catches what the static layer would have caught."""
    frames = list(frames)
    n = len(frames)
    g = ast_guard.check(source)
    empty = [None] * n
    if guard and not g.ok:
        return SandboxResult(valid=False, reason="ast_guard", predictions=empty, metrics=[[None, None]] * n,
                             guard=g.to_dict(), runs=0)

    t0 = time.time()
    runs: List[Dict[str, object]] = []
    n_runs = 2 if determinism_check else 1
    for _ in range(n_runs):
        wd = _write_workdir(source, frames)
        try:
            runs.append(_run_child(wd, timeout_s, memory_mb))
        finally:
            if not keep_workdir:
                shutil.rmtree(wd, ignore_errors=True)
        if runs[-1].get("timeout") or runs[-1].get("harness_error") or not runs[-1].get("loaded"):
            break  # no point running twice

    first = runs[0]
    base = dict(guard=g.to_dict(), runs=len(runs), elapsed_s=round(time.time() - t0, 4),
                child_stdout=first.get("stdout", ""), child_stderr=first.get("stderr", ""))
    if first.get("timeout"):
        return SandboxResult(valid=False, reason="timeout", predictions=empty, metrics=[[None, None]] * n, **base)
    if first.get("harness_error"):
        return SandboxResult(valid=False, reason="harness_error", predictions=empty, metrics=[[None, None]] * n,
                             load_error=str(first["harness_error"]), **base)

    events = list(first.get("events", []))
    denied = [e for e in events if e.get("kind") == "denied"]
    logged = [e for e in events if e.get("kind") == "logged"]
    if not first.get("loaded"):
        return SandboxResult(valid=False, reason="load_error", predictions=empty, metrics=[[None, None]] * n,
                             denied_events=denied, logged_events=logged, load_error=first.get("load_error"), **base)

    preds = list(first["predictions"])
    deterministic: Optional[bool] = None
    if len(runs) == 2:
        second = runs[1]
        deterministic = (second.get("loaded") and second.get("predictions") == preds
                         and not second.get("timeout"))
        denied += [e for e in second.get("events", []) if e.get("kind") == "denied"]
    valid = deterministic is not False
    return SandboxResult(valid=valid, reason=None if valid else "nondeterministic", predictions=preds,
                         metrics=list(first.get("metrics", [])), denied_events=denied, logged_events=logged,
                         frame_errors=sum(1 for p in preds if p is None),
                         error_samples=list(first.get("errors", []))[:10], deterministic=deterministic, **base)
