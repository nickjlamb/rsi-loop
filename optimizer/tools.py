"""The optimiser's tools, as an injected interface.

The loop supplies `run_visible_eval`; this package never imports the evaluator
(design E.2 dependency direction). The callable takes candidate source and
returns the visible report as a plain dict (VisibleReport.to_dict()) computed
on the PUBLIC view of V at the arm's detail level."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

VisibleEval = Callable[[str], Dict[str, object]]
MAX_LOCAL_EVALS = 4


@dataclass(frozen=True)
class ToolBox:
    run_visible_eval: VisibleEval
    max_local_evals: int = MAX_LOCAL_EVALS
