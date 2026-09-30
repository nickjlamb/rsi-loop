"""The parametric no-LLM baseline (D.5) runs through the same loop, passes the
sandbox, cannot memorise, and replays identically on resume."""

import hashlib
import json

from baselines.parametric import GEN0, Params, params_from_source
from loop.config import RunConfig
from loop.run import run_trajectory
from sandbox import ast_guard


def test_family_members_pass_the_guard_and_round_trip():
    for p in (GEN0, Params(head=23.5, wrist=57.0, ref_axis="torso", hand_axis="pinky", roll_correction=True)):
        src = p.source()
        assert ast_guard.check(src).ok
        assert params_from_source(src) == Params(**{**p.__dict__, "head": round(p.head, 3), "wrist": round(p.wrist, 3)})


def cfg(root, arm, gens=6):
    return RunConfig(run_id="p", arm=arm, seed=1, model="parametric", provider="scripted", generations=gens,
                     artifacts_root=root, mock=True)


def test_baseline_trajectory_and_resume_identity(tmp_path):
    full, split = tmp_path / "a", tmp_path / "b"
    st = run_trajectory(cfg(full, "B", 6), quiet=True)
    assert len(st.summaries) == 6 and all(s.outcome == "submitted" for s in st.summaries)
    assert all(s.guard_violations == 0 and s.denied_events == 0 for s in st.summaries)
    run_trajectory(cfg(split, "B", 3), quiet=True)
    run_trajectory(cfg(split, "B", 6), quiet=True)
    dig = lambda root: {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(root.rglob("*")) if p.is_file() and p.name not in ("timing.json", "trajectory.json")}
    assert dig(cfg(full, "B").trajectory_dir) == dig(cfg(split, "B").trajectory_dir)
    traj = json.loads((cfg(full, "B").trajectory_dir / "trajectory.json").read_text())
    assert traj["provider"] == "parametric" and traj["config"]["model"] == "parametric"


def test_baseline_arm_A_self_report_is_well_formed(tmp_path):
    st = run_trajectory(cfg(tmp_path, "A", 3), quiet=True)
    assert all(s.self_report_discrepancy is not None for s in st.summaries)
