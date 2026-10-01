"""Seed hygiene, enforced by code rather than discipline (as in Observer Zero).

Confirmatory seeds 1000–1009 cannot be run — not even generated for a live
trajectory — until DESIGN_FROZEN is flipped to True in a dedicated commit
that also tags the harness and commits experiments/preregistration.md."""

DESIGN_FROZEN = True                   # frozen 1 October 2026; see experiments/preregistration.md
FREEZE_TAG = "v2.0-freeze"
DELTA = 0.025                          # 2 x SE of G at generation 0 (0.0122-0.0123 on pilot seeds 1-3); fixed 30 Sep 2026
PILOT_SEEDS = (1, 2, 3)
CONFIRMATORY_SEEDS = tuple(range(1000, 1010))


class SeedHygieneError(RuntimeError):
    pass


def check_seed(seed: int, *, mock: bool = False) -> None:
    if seed in CONFIRMATORY_SEEDS and not DESIGN_FROZEN and not mock:
        raise SeedHygieneError(f"seed {seed} is a confirmatory seed and the design is not frozen "
                               f"(loop/freeze.py DESIGN_FROZEN=False)")
