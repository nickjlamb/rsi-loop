"""Posture-risk policy, version 0.

Two geometric rules on a single frame of landmarks:

    1. Forward-head angle: deviation of the shoulder->ear vector from the
       vertical (image) axis, in degrees.
    2. Wrist deviation angle: angle between the forearm vector (elbow->wrist)
       and the metacarpal vector (wrist->midpoint(index_mcp, pinky_mcp)).

Either rule exceeding its threshold gives "High Strain".
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

from policy.contract import Label, Landmark, LandmarkSet, RiskAssessment

# ---------------------------------------------------------------------------
# Tunable thresholds (v2 — degrees)
# ---------------------------------------------------------------------------

FORWARD_HEAD_ANGLE_THRESHOLD_DEG: float = 20.0
WRIST_DEVIATION_ANGLE_THRESHOLD_DEG: float = 50.0

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

Vec2 = Tuple[float, float]


def _vec(a: Landmark, b: Landmark) -> Vec2:
    return (b["x"] - a["x"], b["y"] - a["y"])


def _midpoint(a: Landmark, b: Landmark) -> Dict[str, float]:
    return {"x": (a["x"] + b["x"]) / 2.0, "y": (a["y"] + b["y"]) / 2.0}


def _angle_between(u: Vec2, v: Vec2) -> float:
    """Unsigned angle between two 2D vectors, in degrees, in [0, 180]."""
    nu = math.hypot(*u)
    nv = math.hypot(*v)
    if nu == 0.0 or nv == 0.0:
        return 0.0
    cos_t = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
    return math.degrees(math.acos(cos_t))


def _forward_head_angle_deg(ear: Landmark, shoulder: Landmark) -> float:
    """Deviation of the shoulder→ear vector from the image's vertical axis."""
    dx = ear["x"] - shoulder["x"]
    dy = shoulder["y"] - ear["y"]   # positive when ear is above shoulder
    return math.degrees(math.atan2(abs(dx), abs(dy)))


def _wrist_deviation_angle_deg(
    elbow: Landmark, wrist: Landmark, index_mcp: Landmark, pinky_mcp: Landmark
) -> float:
    """Angle between the forearm and the metacarpal axis."""
    forearm = _vec(elbow, wrist)
    hand_axis = _vec(wrist, _midpoint(index_mcp, pinky_mcp))
    return _angle_between(forearm, hand_axis)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assess(landmarks: LandmarkSet) -> RiskAssessment:
    """Classify a single frame's landmarks as Safe / High Strain."""

    fwd_head = _forward_head_angle_deg(landmarks["ear"], landmarks["shoulder"])
    wrist_dev = _wrist_deviation_angle_deg(
        landmarks["elbow"],
        landmarks["wrist"],
        landmarks["index_mcp"],
        landmarks["pinky_mcp"],
    )

    triggered: list[str] = []
    if fwd_head > FORWARD_HEAD_ANGLE_THRESHOLD_DEG:
        triggered.append("forward_head")
    if wrist_dev > WRIST_DEVIATION_ANGLE_THRESHOLD_DEG:
        triggered.append("wrist_deviation")

    label: Label = "High Strain" if triggered else "Safe"
    return RiskAssessment(
        label=label,
        forward_head_metric=fwd_head,
        wrist_deviation_metric=wrist_dev,
        triggered_rules=tuple(triggered),
    )
