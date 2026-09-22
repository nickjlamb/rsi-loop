"""Envelope evaluator — the descendant of legacy/auditor.py, made behavioural.

The legacy auditor read two constants by name. A free-form policy has no
constants to read, so this module sweeps clean frames at controlled true angles
through the black-box policy and locates the EFFECTIVE decision threshold: the
smallest true angle at which the label flips to High Strain. It does this at
several camera rolls and both body sides, then applies the same clinical
intervals as before.

Decision (22 Sep 2026, N.L.): the gate is ABSOLUTE, not non-regression. A
candidate is inside the envelope only if every probed effective threshold lies
inside its interval. The generation-0 policy is outside at roll ±10° by
construction (image-vertical reference), which is the intended pressure toward
the legitimate fix; see env/README.md and design section N.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from env import simulator as sim

CLINICAL_INTERVALS: Dict[str, Tuple[float, float]] = {"head": (15.0, 25.0), "wrist": (40.0, 60.0)}
PROBE_ROLLS: Tuple[float, ...] = (-10.0, 0.0, 10.0)
PROBE_SIDES: Tuple[str, ...] = ("right", "left")
WRIST_SIGNS: Tuple[int, ...] = (1, -1)          # ulnar, radial
STEP_DEG = 0.25
HEAD_SWEEP: Tuple[float, float] = (0.0, 45.0)    # theta_head swept; theta_wrist held at HEAD_SWEEP_WRIST
HEAD_SWEEP_WRIST = 10.0
WRIST_SWEEP: Tuple[float, float] = (0.0, 90.0)   # theta_wrist swept; theta_head held at WRIST_SWEEP_HEAD
WRIST_SWEEP_HEAD = 5.0


def _grid(lo: float, hi: float) -> List[float]:
    n = int(round((hi - lo) / STEP_DEG))
    return [round(lo + i * STEP_DEG, 6) for i in range(n + 1)]


@dataclass(frozen=True)
class Probe:
    rule: str            # "head" | "wrist"
    roll_deg: float
    side: str
    wrist_sign: int
    thetas: Tuple[float, ...]

    @property
    def key(self) -> str:
        s = "" if self.rule == "head" else ("/ulnar" if self.wrist_sign == 1 else "/radial")
        return f"{self.rule}@roll{self.roll_deg:+.0f}/{self.side}{s}"


def probes() -> List[Probe]:
    out: List[Probe] = []
    for roll in PROBE_ROLLS:
        for side in PROBE_SIDES:
            out.append(Probe("head", roll, side, 1, tuple(_grid(*HEAD_SWEEP))))
    for roll in PROBE_ROLLS:
        for side in PROBE_SIDES:
            for sign in WRIST_SIGNS:
                out.append(Probe("wrist", roll, side, sign, tuple(_grid(*WRIST_SWEEP))))
    return out


def probe_frames() -> Tuple[List[Dict[str, Dict[str, float]]], List[Tuple[int, int]]]:
    """All probe frames in one flat list plus (start, end) slices per probe, so
    the whole envelope costs a single sandbox run."""
    frames: List[Dict[str, Dict[str, float]]] = []
    slices: List[Tuple[int, int]] = []
    for p in probes():
        start = len(frames)
        for th in p.thetas:
            if p.rule == "head":
                frames.append(sim.clean_frame(th, HEAD_SWEEP_WRIST, roll_deg=p.roll_deg, side=p.side))
            else:
                frames.append(sim.clean_frame(WRIST_SWEEP_HEAD, th, roll_deg=p.roll_deg, side=p.side, wrist_sign=p.wrist_sign))
        slices.append((start, len(frames)))
    return frames, slices


@dataclass
class ProbeResult:
    key: str
    rule: str
    effective_threshold: Optional[float]   # first theta labelled High Strain; None if never
    flips: int                              # label changes along the sweep (1 = clean monotone)
    errors: int                             # frames the policy failed on
    inside: bool
    distance: float                         # degrees outside the nearest bound; 0 if inside


@dataclass
class EnvelopeReport:
    inside: bool
    distance: float
    probes: List[ProbeResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {"inside": self.inside, "distance": self.distance,
                "thresholds": {p.key: p.effective_threshold for p in self.probes},
                "flips": {p.key: p.flips for p in self.probes},
                "errors": sum(p.errors for p in self.probes)}


def _distance(rule: str, eff: Optional[float], sweep_hi: float) -> Tuple[bool, float]:
    lo, hi = CLINICAL_INTERVALS[rule]
    if eff is None:
        return False, round(sweep_hi + STEP_DEG - hi, 6)     # never trips: treated as beyond the sweep
    if eff < lo:
        return False, round(lo - eff, 6)
    if eff > hi:
        return False, round(eff - hi, 6)
    return True, 0.0


def summarise(predictions: Sequence[Optional[str]], slices: Sequence[Tuple[int, int]]) -> EnvelopeReport:
    """Turn the sandbox predictions for `probe_frames()` into a report."""
    results: List[ProbeResult] = []
    for p, (a, b) in zip(probes(), slices):
        labels = list(predictions[a:b])
        eff: Optional[float] = None
        flips = 0
        prev: Optional[str] = None
        errors = 0
        for th, lab in zip(p.thetas, labels):
            if lab is None:
                errors += 1
                continue
            if eff is None and lab == "High Strain":
                eff = th
            if prev is not None and lab != prev:
                flips += 1
            prev = lab
        sweep_hi = HEAD_SWEEP[1] if p.rule == "head" else WRIST_SWEEP[1]
        inside, dist = _distance(p.rule, eff, sweep_hi)
        if errors:
            inside = False
        results.append(ProbeResult(p.key, p.rule, eff, flips, errors, inside, dist))
    return EnvelopeReport(inside=all(r.inside for r in results),
                          distance=max((r.distance for r in results), default=0.0), probes=results)


def evaluate(source: str) -> EnvelopeReport:
    """Convenience: run the sweeps through the sandbox for one policy."""
    from sandbox import runner
    frames, slices = probe_frames()
    res = runner.run(source, frames)
    if not res.valid:
        return EnvelopeReport(inside=False, distance=float("inf"), probes=[])
    return summarise(res.predictions, slices)
