"""Run configuration. Everything that could change a trajectory's behaviour is
here and is written verbatim into trajectory.json."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_ROOT = ROOT / "artifacts"
GENERATIONS = 20


@dataclass(frozen=True)
class RunConfig:
    run_id: str
    arm: str                                   # A | B | C | D
    seed: int
    model: str                                 # provider model id, or "scripted"
    provider: str = "perplexity-agent"          # perplexity-agent | scripted
    generations: int = GENERATIONS
    notes_enabled: bool = True                  # the recursive channel (design D.4 secondary factor)
    visible_detail: str = "per-case"            # design D.3 switch VISIBLE_DETAIL
    eval_source_visible: bool = True            # design D.3 switch EVAL_SOURCE_VISIBLE
    max_local_evals: int = 4
    max_output_tokens: int = 32000              # reasoning tokens count against this; Sonnet 5 uses 12-16k per reply (pilot-02)
    reasoning_effort: Optional[str] = None       # None = API default; "low"/"medium"/"high" if ever set, recorded per trajectory
    temperature: Optional[float] = None         # None = provider default (Agent API default is 1)
    max_cost_usd: float = 10.0                  # per-trajectory guard; halts with a recorded reason
    artifacts_root: Path = ARTIFACTS_ROOT
    mock: bool = False                          # scripted provider: no spend, seed hygiene relaxed

    def __post_init__(self):
        assert self.arm in "ABCD" and len(self.arm) == 1
        assert self.visible_detail in ("aggregate", "per-case")

    @property
    def trajectory_dir(self) -> Path:
        return self.artifacts_root / self.run_id / f"arm_{self.arm}" / f"seed_{self.seed:04d}"

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        d["artifacts_root"] = str(self.artifacts_root)
        return d
