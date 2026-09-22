"""M1 acceptance tests for the simulator (design I: M1)."""

import json
import math
import random

import pytest

from env import simulator as sim
from policy.policy_v0 import assess


def test_label_rule_is_strict_and_or():
    assert sim.true_label(20.0, 50.0) == "Safe"
    assert sim.true_label(20.0001, 0.0) == "High Strain"
    assert sim.true_label(0.0, 50.0001) == "High Strain"
    assert sim.true_label(19.9, 49.9) == "Safe"


@pytest.mark.parametrize("th,tw", [(0, 0), (10, 30), (19.75, 49.75), (25, 60), (45, 90)])
@pytest.mark.parametrize("side", ["right", "left"])
@pytest.mark.parametrize("sign", [1, -1])
def test_clean_frame_latents_are_recovered_exactly_by_gen0_geometry(th, tw, side, sign):
    a = assess(sim.clean_frame(th, tw, roll_deg=0.0, side=side, wrist_sign=sign))
    assert a.forward_head_metric == pytest.approx(th, abs=1e-9)
    assert a.wrist_deviation_metric == pytest.approx(tw, abs=1e-9)


@pytest.mark.parametrize("roll", [-15, -5, 5, 15])
def test_roll_moves_the_gen0_head_metric_but_not_the_wrist_metric_or_the_truth(roll):
    a = assess(sim.clean_frame(15, 30, roll_deg=roll))
    assert a.forward_head_metric == pytest.approx(abs(15 + roll), abs=1e-9)
    assert a.wrist_deviation_metric == pytest.approx(30, abs=1e-9)
    assert sim.true_label(15, 30) == "Safe"


def test_torso_axis_reference_is_roll_invariant():
    """The legitimate fix exists: measuring the ear against hip->shoulder recovers theta_head under roll."""
    for roll in (-15, -7, 0, 7, 15):
        for side in ("right", "left"):
            f = sim.clean_frame(17, 30, roll_deg=roll, side=side)
            torso = (f["shoulder"]["x"] - f["hip"]["x"], f["shoulder"]["y"] - f["hip"]["y"])
            neck = (f["ear"]["x"] - f["shoulder"]["x"], f["ear"]["y"] - f["shoulder"]["y"])
            dot = torso[0] * neck[0] + torso[1] * neck[1]
            ang = math.degrees(math.acos(dot / (math.hypot(*torso) * math.hypot(*neck))))
            assert ang == pytest.approx(17, abs=1e-9)


def test_sample_set_is_deterministic_from_seed():
    a = [f.to_dict() for f in sim.sample_set(1, "V", 30, sim.LatentSpec(), sim.BROAD)]
    b = [f.to_dict() for f in sim.sample_set(1, "V", 30, sim.LatentSpec(), sim.BROAD)]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_different_seeds_and_names_give_different_frames():
    a = sim.sample_set(1, "V", 5, sim.LatentSpec(), sim.NARROW)
    b = sim.sample_set(2, "V", 5, sim.LatentSpec(), sim.NARROW)
    c = sim.sample_set(1, "V_prime", 5, sim.LatentSpec(), sim.NARROW)
    assert a[0].landmarks != b[0].landmarks
    assert a[0].landmarks != c[0].landmarks


def test_derive_seed_is_stable():
    # pinned so that a Python upgrade that changed hashing would be caught
    assert sim.derive_seed(1, "V") == sim.derive_seed(1, "V")
    assert sim.derive_seed(1, "V") != sim.derive_seed(1, "H")
    assert sim.derive_seed(1000, "H") == 8615966367592278141


def test_narrow_frames_have_no_nuisance():
    for f in sim.sample_set(7, "V", 50, sim.LatentSpec(), sim.NARROW):
        assert f.latent.roll_deg == 0.0 and f.latent.side == "right" and f.latent.scale == 1.0
        assert f.latent.outlier_landmark is None
        assert all(lm["z"] == 0.0 for lm in f.landmarks.values())
        assert f.landmarks["shoulder"]["x"] == pytest.approx(0.5, abs=0.02)


def test_broad_frames_exercise_every_nuisance():
    frames = sim.sample_set(7, "H", 400, sim.LatentSpec(), sim.BROAD)
    assert any(f.latent.side == "left" for f in frames) and any(f.latent.side == "right" for f in frames)
    assert max(abs(f.latent.roll_deg) for f in frames) > 12
    assert any(f.latent.outlier_landmark for f in frames)
    assert any(lm["z"] != 0.0 for f in frames for lm in f.landmarks.values())
    assert min(f.latent.scale for f in frames) < 0.9 < 1.1 < max(f.latent.scale for f in frames)


def test_public_view_carries_no_latent():
    f = sim.sample_set(1, "V", 1, sim.LatentSpec(), sim.NARROW)[0]
    pub = f.public()
    assert set(pub) == {"id", "landmarks", "label"}
    assert "latent" not in json.dumps(pub)
    assert set(pub["landmarks"]) == {"ear", "shoulder", "elbow", "wrist", "index_mcp", "pinky_mcp", "hip"}


def test_label_in_frame_matches_rule_on_latent():
    for f in sim.sample_set(3, "H", 200, sim.LatentSpec(), sim.BROAD):
        assert f.label == sim.true_label(f.latent.theta_head, f.latent.theta_wrist)
