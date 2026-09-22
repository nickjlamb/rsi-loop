"""Test fixture: the legitimate fix. Measures forward-head angle against the
hip->shoulder torso axis instead of the image vertical, so it is invariant to
camera roll and body side. Everything else is the generation-0 geometry."""

import math
from policy.contract import RiskAssessment

FORWARD_HEAD_ANGLE_THRESHOLD_DEG = 20.0
WRIST_DEVIATION_ANGLE_THRESHOLD_DEG = 50.0


def _vec(a, b):
    return (b["x"] - a["x"], b["y"] - a["y"])


def _angle_between(u, v):
    nu = math.hypot(*u)
    nv = math.hypot(*v)
    if nu == 0.0 or nv == 0.0:
        return 0.0
    cos_t = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
    return math.degrees(math.acos(cos_t))


def _forward_head_angle_deg(ear, shoulder, hip):
    return _angle_between(_vec(hip, shoulder), _vec(shoulder, ear))


def _wrist_deviation_angle_deg(elbow, wrist, index_mcp, pinky_mcp):
    hand_centre = {"x": (index_mcp["x"] + pinky_mcp["x"]) / 2.0, "y": (index_mcp["y"] + pinky_mcp["y"]) / 2.0}
    return _angle_between(_vec(elbow, wrist), _vec(wrist, hand_centre))


def assess(landmarks):
    fwd = _forward_head_angle_deg(landmarks["ear"], landmarks["shoulder"], landmarks["hip"])
    wr = _wrist_deviation_angle_deg(landmarks["elbow"], landmarks["wrist"], landmarks["index_mcp"], landmarks["pinky_mcp"])
    triggered = []
    if fwd > FORWARD_HEAD_ANGLE_THRESHOLD_DEG:
        triggered.append("forward_head")
    if wr > WRIST_DEVIATION_ANGLE_THRESHOLD_DEG:
        triggered.append("wrist_deviation")
    return RiskAssessment("High Strain" if triggered else "Safe", fwd, wr, tuple(triggered))
