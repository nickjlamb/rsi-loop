"""
RSI risk detector — v2.

Cycle 1 of the RSI Loop revealed that v1's signed horizontal-offset heuristic
for wrist deviation was direction-blind: it caught ulnar bends (toward +x) but
missed radial bends (toward -x), failing scenario S06.

v2 replaces both crude offsets with proper trigonometric angles:

    1. Forward-head angle: deviation of the shoulder→ear vector from the
       vertical (image) axis, in degrees. Symmetric in left/right.
    2. Wrist deviation angle: angle between the forearm vector (elbow→wrist)
       and the metacarpal vector (wrist→midpoint(index_mcp, pinky_mcp)).
       Direction-agnostic, so a sideways bend in either direction registers.

The optional MediaPipe webcam pipeline is unchanged; only the geometry is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Literal, Mapping, Optional, Tuple

Label = Literal["Safe", "High Strain"]
Landmark = Mapping[str, float]
LandmarkSet = Mapping[str, Landmark]


# ---------------------------------------------------------------------------
# Tunable thresholds (v2 — degrees)
# ---------------------------------------------------------------------------

FORWARD_HEAD_ANGLE_THRESHOLD_DEG: float = 20.0
WRIST_DEVIATION_ANGLE_THRESHOLD_DEG: float = 50.0


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RiskAssessment:
    label: Label
    forward_head_metric: float        # degrees off vertical
    wrist_deviation_metric: float     # degrees between forearm and hand axes
    triggered_rules: tuple[str, ...]

    def is_high_strain(self) -> bool:
        return self.label == "High Strain"


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


# ---------------------------------------------------------------------------
# Optional live webcam pipeline (lazy, not required for tests)
# ---------------------------------------------------------------------------

def assess_from_webcam(camera_index: int = 0) -> Optional[RiskAssessment]:
    """Grab one frame from the webcam, run MediaPipe, return an assessment.

    Returns None if MediaPipe / OpenCV aren't installed or if no pose was
    detected. Imported lazily so the rest of the project stays lightweight.
    """
    try:
        import cv2  # type: ignore
        import mediapipe as mp  # type: ignore
    except ImportError:
        return None

    mp_pose = mp.solutions.pose
    mp_hands = mp.solutions.hands

    cap = cv2.VideoCapture(camera_index)
    try:
        ok, frame = cap.read()
        if not ok:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        with mp_pose.Pose(static_image_mode=True) as pose, \
             mp_hands.Hands(static_image_mode=True, max_num_hands=1) as hands:
            pose_res = pose.process(rgb)
            hand_res = hands.process(rgb)
            if not pose_res.pose_landmarks or not hand_res.multi_hand_landmarks:
                return None
            pl = pose_res.pose_landmarks.landmark
            hl = hand_res.multi_hand_landmarks[0].landmark
            landmarks: Dict[str, Dict[str, float]] = {
                "ear":       {"x": pl[8].x,  "y": pl[8].y,  "z": pl[8].z},
                "shoulder":  {"x": pl[12].x, "y": pl[12].y, "z": pl[12].z},
                "elbow":     {"x": pl[14].x, "y": pl[14].y, "z": pl[14].z},
                "wrist":     {"x": pl[16].x, "y": pl[16].y, "z": pl[16].z},
                "index_mcp": {"x": hl[5].x,  "y": hl[5].y,  "z": hl[5].z},
                "pinky_mcp": {"x": hl[17].x, "y": hl[17].y, "z": hl[17].z},
            }
            return assess(landmarks)
    finally:
        cap.release()
