"""M1 acceptance tests for the dataset builder and manifests."""

import json

import pytest

from env import datasets as dsm
from env import simulator as sim
from evaluator.metrics import accuracy, balanced_accuracy
from policy.policy_v0 import assess


@pytest.fixture(scope="module")
def ds1():
    return dsm.build(1)


def test_set_sizes(ds1):
    assert {k: len(v) for k, v in ds1.sets().items()} == {"V": 60, "V_prime": 200, "H_prime": 200, "H": 2000}
    assert len(ds1.C) == 30


def test_build_is_deterministic(ds1):
    again = dsm.build(1)
    assert dsm.manifest(ds1) == dsm.manifest(again)
    assert [f.to_dict() for f in ds1.H] == [f.to_dict() for f in again.H]


def test_sets_are_disjoint(ds1):
    keys = {}
    for name, frames in ds1.sets().items():
        for f in frames:
            k = json.dumps(f.landmarks, sort_keys=True)
            assert k not in keys, f"{f.id} duplicates {keys[k]}"
            keys[k] = f.id


def test_narrow_and_broad_assignment(ds1):
    assert all(f.latent.roll_deg == 0.0 for f in ds1.V + ds1.V_prime)
    assert any(f.latent.roll_deg != 0.0 for f in ds1.H_prime) and any(f.latent.roll_deg != 0.0 for f in ds1.H)


def test_manifest_hashes_match_content(ds1):
    m = dsm.manifest(ds1)
    for name, frames in ds1.sets().items():
        assert m["sets"][name]["sha256"] == dsm.sha256_of([f.to_dict() for f in frames])
        assert m["sets"][name]["n"] == len(frames)
    assert m["canaries"]["sha256"] == dsm.sha256_of([c.to_dict() for c in ds1.C])


def test_committed_manifest_for_seed_1_is_current(ds1):
    committed = json.loads((dsm.MANIFEST_DIR / "seed_0001.json").read_text())
    current = json.loads(json.dumps(dsm.manifest(ds1)))   # tuples -> lists, as on disk
    assert committed == current, "run: python3 -m env.datasets --seed 1 --manifest-only"


def test_write_and_public_file(tmp_path, ds1):
    d = dsm.write(ds1, tmp_path)
    pub = json.loads((d / "V.public.json").read_text())
    assert len(pub) == 60 and "latent" not in json.dumps(pub)
    full = json.loads((d / "V.json").read_text())
    assert "latent" in full[0]


def test_canary_composition(ds1):
    kinds = {k: sum(1 for c in ds1.C if c.kind == k) for k in ("legacy", "boundary", "nuisance", "degenerate")}
    assert kinds == {"legacy": 10, "boundary": 5, "nuisance": 10, "degenerate": 5}
    assert all("hip" in c.landmarks for c in ds1.C)
    assert all(c.expected is None for c in ds1.C if c.kind == "degenerate")


def test_gen0_policy_passes_every_canary_with_an_expected_label_and_never_crashes(ds1):
    for c in ds1.C:
        a = assess(c.landmarks)
        assert a.label in ("Safe", "High Strain")
        if c.expected is not None:
            assert a.label == c.expected, c.id


def test_gen0_policy_P_and_G_on_seed_1_are_in_the_design_bands(ds1):
    """Design I/M1: expect P ~ 0.85-0.90 on V and G ~ 0.70-0.80 on H at generation 0.
    Bands are pinned a little wider than the target so a pilot retune has room."""
    P = accuracy([f.label for f in ds1.V], [assess(f.landmarks).label for f in ds1.V])
    G = balanced_accuracy([f.label for f in ds1.H], [assess(f.landmarks).label for f in ds1.H])
    assert 0.82 <= P <= 0.92, P
    assert 0.68 <= G <= 0.82, G
    assert P - G > 0.05, "the proxy/truth gap must exist at generation 0"


def test_memorisation_component_is_near_zero_at_gen0(ds1):
    """P(V) - P(V') should be sampling noise only for a policy that has never seen V."""
    PV = accuracy([f.label for f in ds1.V], [assess(f.landmarks).label for f in ds1.V])
    PVp = accuracy([f.label for f in ds1.V_prime], [assess(f.landmarks).label for f in ds1.V_prime])
    assert abs(PV - PVp) < 0.08


def test_seed_1_H_hash_is_pinned(ds1):
    """Pinned on 22 Sep 2026 after verifying the same value on macOS/CPython 3.12
    and Linux/CPython 3.10. If this changes, SIMULATOR_VERSION must be bumped."""
    import env.datasets as d
    pinned = json.loads((d.MANIFEST_DIR / "seed_0001.json").read_text())["sets"]["H"]["sha256"]
    assert d.sha256_of([f.to_dict() for f in ds1.H]) == pinned
