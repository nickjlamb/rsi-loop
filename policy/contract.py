"""The policy's return contract — unchanged from the legacy detector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

Label = Literal["Safe", "High Strain"]
Landmark = Mapping[str, float]
LandmarkSet = Mapping[str, Landmark]

#: Landmarks every frame carries. `hip` is new in RSI Loop 2 (it makes the torso
#: axis recoverable); the generation-0 policy ignores it.
LANDMARK_NAMES: tuple[str, ...] = (
    "ear", "shoulder", "elbow", "wrist", "index_mcp", "pinky_mcp", "hip",
)


@dataclass(frozen=True)
class RiskAssessment:
    label: Label
    forward_head_metric: float        # degrees off vertical
    wrist_deviation_metric: float     # degrees between forearm and hand axes
    triggered_rules: tuple[str, ...]

    def is_high_strain(self) -> bool:
        return self.label == "High Strain"
