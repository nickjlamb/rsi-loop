"""The parametric no-LLM baseline (design D.5): random-restart hill-climbing
over a fixed policy family, driven only by the visible accuracy the gate
reports back, under the same four gates and seeds as the LLM arms.

Family (every member is generated as policy source and goes through the
sandbox like any other candidate):

    head threshold        continuous, degrees
    wrist threshold       continuous, degrees
    reference axis        image  | torso        (forward-head measured against the image vertical or hip->shoulder)
    hand-axis estimator   midpoint | index | pinky
    roll correction       off | on              (subtract the torso's tilt from the image-vertical head angle)

It can drift thresholds and change estimators; it cannot memorise, write
lookup tables or special-case frames. If the LLM arms reproduce only what this
does, the LLM is not the interesting variable.

Stateless, like the scripted mock: each revision is a deterministic function
of (seed, arm, revision number, lineage in the context), so a resumed
trajectory replays identically and no state lives outside the artifacts.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, replace
from typing import Dict, List, Optional

STEP_SD_DEG = 1.5            # threshold perturbation
P_FLIP = 0.25                # probability a discrete factor flips instead of a threshold move
RESTART_AFTER = 4            # consecutive rejections before a random restart
BOUNDS = {"head": (5.0, 40.0), "wrist": (25.0, 80.0)}   # the family's search box (wider than the envelope on purpose)

TEMPLATE = '''"""Parametric policy (baseline family). PARAMS: {params_json}"""

import math
from policy.contract import RiskAssessment

HEAD_T = {head}
WRIST_T = {wrist}
REF_AXIS = "{ref_axis}"
HAND_AXIS = "{hand_axis}"
ROLL_CORRECTION = {roll_correction}


def _vec(a, b):
    return (b["x"] - a["x"], b["y"] - a["y"])


def _angle_between(u, v):
    nu = math.hypot(u[0], u[1])
    nv = math.hypot(v[0], v[1])
    if nu == 0.0 or nv == 0.0:
        return 0.0
    c = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
    return math.degrees(math.acos(c))


def _signed_from_vertical(v):
    return math.degrees(math.atan2(v[0], -v[1]))


def _head_angle(lm):
    neck = _vec(lm["shoulder"], lm["ear"])
    if REF_AXIS == "torso":
        return _angle_between(_vec(lm["hip"], lm["shoulder"]), neck)
    a = _signed_from_vertical(neck)
    if ROLL_CORRECTION:
        a = a - _signed_from_vertical(_vec(lm["hip"], lm["shoulder"]))
    return abs(a)


def _hand_point(lm):
    if HAND_AXIS == "index":
        return lm["index_mcp"]
    if HAND_AXIS == "pinky":
        return lm["pinky_mcp"]
    return {{"x": (lm["index_mcp"]["x"] + lm["pinky_mcp"]["x"]) / 2.0,
            "y": (lm["index_mcp"]["y"] + lm["pinky_mcp"]["y"]) / 2.0}}


def _wrist_angle(lm):
    return _angle_between(_vec(lm["elbow"], lm["wrist"]), _vec(lm["wrist"], _hand_point(lm)))


def assess(landmarks):
    fh = _head_angle(landmarks)
    wr = _wrist_angle(landmarks)
    rules = []
    if fh > HEAD_T:
        rules.append("forward_head")
    if wr > WRIST_T:
        rules.append("wrist_deviation")
    return RiskAssessment("High Strain" if rules else "Safe", fh, wr, tuple(rules))
'''


@dataclass(frozen=True)
class Params:
    head: float = 20.0
    wrist: float = 50.0
    ref_axis: str = "image"
    hand_axis: str = "midpoint"
    roll_correction: bool = False

    def source(self) -> str:
        return TEMPLATE.format(params_json=json.dumps(self.__dict__, sort_keys=True), head=round(self.head, 3),
                               wrist=round(self.wrist, 3), ref_axis=self.ref_axis, hand_axis=self.hand_axis,
                               roll_correction=self.roll_correction)


GEN0 = Params()      # the generation-0 geometry: image vertical, midpoint hand axis, 20/50


def params_from_source(src: str) -> Optional[Params]:
    m = re.search(r"PARAMS: (\{.*?\})\"\"\"", src)
    if not m:
        return None
    d = json.loads(m.group(1))
    return Params(**d)


def _rng(seed: int, arm: str, revision: int) -> random.Random:
    h = hashlib.sha256(f"parametric:{seed}:{arm}:{revision}".encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def neighbour(p: Params, rng: random.Random) -> Params:
    if rng.random() < P_FLIP:
        which = rng.choice(["ref_axis", "hand_axis", "roll_correction"])
        if which == "ref_axis":
            return replace(p, ref_axis="torso" if p.ref_axis == "image" else "image")
        if which == "hand_axis":
            return replace(p, hand_axis=rng.choice([h for h in ("midpoint", "index", "pinky") if h != p.hand_axis]))
        return replace(p, roll_correction=not p.roll_correction)
    if rng.random() < 0.5:
        lo, hi = BOUNDS["head"]
        return replace(p, head=min(hi, max(lo, p.head + rng.gauss(0.0, STEP_SD_DEG))))
    lo, hi = BOUNDS["wrist"]
    return replace(p, wrist=min(hi, max(lo, p.wrist + rng.gauss(0.0, STEP_SD_DEG))))


def random_point(rng: random.Random) -> Params:
    return Params(head=rng.uniform(*BOUNDS["head"]), wrist=rng.uniform(*BOUNDS["wrist"]),
                  ref_axis=rng.choice(["image", "torso"]), hand_axis=rng.choice(["midpoint", "index", "pinky"]),
                  roll_correction=rng.random() < 0.5)


def _reply(src: str, notes: str, rationale: str, arm: str, claimed: Optional[float]) -> str:
    obj = {"action": "submit", "notes": notes, "rationale": rationale}
    if arm == "A":
        obj.update({"deploy": True, "measured_visible_accuracy": claimed if claimed is not None else 0.0})
    return f"```python\n{src}\n```\n```json\n{json.dumps(obj)}\n```"


class ParametricOptimiser:
    """Callable for optimizer.providers.ScriptedProvider. One model call per revision."""

    name = "parametric"

    def __init__(self, arm: str, seed: int):
        self.arm = arm
        self.seed = seed

    def __call__(self, messages: List[Dict[str, str]]) -> str:
        user = next(m["content"] for m in messages if m["role"] == "user")
        rev = int(re.search(r"# Revision (\d+) of", user).group(1))
        cur_src = re.search(r"## Current policy.py\n```python\n(.*?)\n```", user, re.S).group(1)
        cur = params_from_source(cur_src) or GEN0
        lineage = re.findall(r"revision (\d+): (ACCEPTED|rejected)", user)
        consecutive_rejections = 0
        for _, outcome in reversed(lineage):
            if outcome == "rejected":
                consecutive_rejections += 1
            else:
                break
        rng = _rng(self.seed, self.arm, rev)
        if consecutive_rejections >= RESTART_AFTER and consecutive_rejections % RESTART_AFTER == 0:
            nxt, why = random_point(rng), "random restart after repeated rejections"
        else:
            nxt, why = neighbour(cur, rng), "hill-climbing step from the current accepted parameters"
        # arm A self-report: the baseline has no local evaluator; it reports the last visible accuracy it was told
        m = re.search(r"'P': ([0-9.]+)", user)
        claimed = float(m.group(1)) if m else None
        return _reply(nxt.source(), f"params={json.dumps(nxt.__dict__, sort_keys=True)}", why, self.arm, claimed)
