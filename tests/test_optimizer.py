"""M4 acceptance tests: the information boundary of the context, the reply
protocol, the revision loop (eval cap, corrections, failures), and the Agent
API request shape (no tools, ever)."""

import json
from pathlib import Path

import pytest

from env import datasets as dsm
from evaluator import visible
from evaluator.bundle import score_candidate
from optimizer import agent, context, protocol
from optimizer.providers import (ProviderError, ScriptedProvider, build_agent_request, extract_cost,
                                 extract_text)
from optimizer.tools import ToolBox

ROOT = Path(__file__).resolve().parent.parent
GEN0 = (ROOT / "policy" / "policy_v0.py").read_text()
TORSO = (ROOT / "tests" / "fixtures" / "policy_torso.py").read_text()


def reply(src, action, **extra):
    return f"```python\n{src}\n```\n```json\n{json.dumps(dict(action=action, notes='n', rationale='r', **extra))}\n```"


@pytest.fixture(scope="module")
def ds1():
    return dsm.build(1)


@pytest.fixture(scope="module")
def Vp(ds1):
    return [f.public() for f in ds1.V]


@pytest.fixture(scope="module")
def report(Vp):
    return visible.evaluate(GEN0, Vp).to_dict()


@pytest.fixture
def tools(Vp):
    return ToolBox(run_visible_eval=lambda s: visible.evaluate(s, Vp).to_dict())


def ctx_for(arm, Vp, report, **kw):
    return context.build(arm=arm, generation=1, current_source=GEN0, notes="remember this", lineage=[],
                         V_public=Vp, report=report, **kw)


# --- context / information boundary -------------------------------------------

def test_context_contains_no_hidden_information(Vp, report):
    for arm in "ABCD":
        c = ctx_for(arm, Vp, report)
        blob = c.system + c.user
        for w in context.FORBIDDEN_IN_CONTEXT:
            assert w not in blob
        assert "V-1-0000" in c.user and "hip" in c.system
        assert "Acceptance rule" in c.system


def test_context_rejects_non_public_frames(ds1, report):
    with pytest.raises(AssertionError):
        context.build(arm="B", generation=1, current_source=GEN0, notes="", lineage=[],
                      V_public=[f.to_dict() for f in ds1.V[:1]], report=report)


def test_arm_texts_are_truthful_and_distinct(Vp, report):
    a, b, c, d = (ctx_for(x, Vp, report).system for x in "ABCD")
    assert "You decide" in a and "measured_visible_accuracy" in a
    assert "hidden holdout" not in b and "not lower than the current version's" in b
    assert "hidden holdout" in c and "never the hidden score" in c
    assert "effective decision thresholds" in d and "canary" in d and "15–25°" in d


def test_notes_toggle_and_detail_levels(Vp, report):
    on = ctx_for("B", Vp, report, notes_enabled=True)
    off = ctx_for("B", Vp, report, notes_enabled=False)
    assert "remember this" in on.user and "remember this" not in off.user
    assert "NOT shown" in off.system
    per = ctx_for("B", Vp, report, visible_detail="per-case")
    agg = ctx_for("B", Vp, report, visible_detail="aggregate")
    assert "Per case" in per.user and "Per case" not in agg.user
    assert len(agg.user) < len(per.user)


def test_prompt_hashes_cover_every_prompt_file(Vp, report):
    h = ctx_for("C", Vp, report).prompt_hashes
    assert set(h) == {"system.md", "environment.md", "arm_A.md", "arm_B.md", "arm_C.md", "arm_D.md"}
    assert all(len(v) == 64 for v in h.values())


def test_lineage_is_rendered(Vp, report):
    lin = [context.LineageEntry(1, True, "accepted", 0.9), context.LineageEntry(2, False, "hidden holdout", 0.95)]
    c = context.build(arm="C", generation=3, current_source=GEN0, notes="", lineage=lin, V_public=Vp, report=report)
    assert "revision 1: ACCEPTED" in c.user and "revision 2: rejected (hidden holdout)" in c.user
    assert "Revision 3 of 20" in c.user


# --- protocol -------------------------------------------------------------------

def test_protocol_parses_a_good_reply():
    r = protocol.parse("Sure.\n" + reply("def assess(lm):\n    return {'label': 'Safe'}", "submit"))
    assert r.ok and r.action == "submit" and r.source.endswith("'Safe'}\n") and r.notes == "n"


@pytest.mark.parametrize("text,needle", [
    ("no blocks", "python block"),
    ("```python\nx=1\n```", "json block"),
    ("```python\nx=1\n```\n```json\n{bad\n```", "does not parse"),
    ("```python\nx=1\n```\n```json\n[1]\n```", "must be an object"),
    ("```python\nx=1\n```\n```json\n{\"action\": \"deploy\"}\n```", "action must be one of"),
    ("```python\nx=1\n```\n```python\ny=2\n```\n```json\n{\"action\": \"submit\"}\n```", "found 2"),
])
def test_protocol_errors(text, needle):
    r = protocol.parse(text)
    assert not r.ok and needle in r.error


def test_protocol_self_report_for_arm_A():
    r = protocol.parse(reply("x=1", "submit"), require_self_report=True)
    assert not r.ok and "deploy" in r.error
    r = protocol.parse(reply("x=1", "submit", deploy=True, measured_visible_accuracy=1.5), require_self_report=True)
    assert not r.ok and "[0, 1]" in r.error
    r = protocol.parse(reply("x=1", "submit", deploy=False, measured_visible_accuracy=0.9), require_self_report=True)
    assert r.ok and r.extra == {"deploy": False, "measured_visible_accuracy": 0.9}
    r = protocol.parse(reply("x=1", "run_visible_eval"), require_self_report=True)
    assert r.ok   # self report is only required on submit


def test_protocol_accepts_an_unlabelled_json_fence():
    r = protocol.parse("```python\nx=1\n```\n```\n{\"action\": \"submit\"}\n```")
    assert r.ok


# --- the revision loop -----------------------------------------------------------

def test_revision_with_one_local_eval_then_submit(Vp, report, tools):
    prov = ScriptedProvider([reply(TORSO, "run_visible_eval"), reply(TORSO, "submit")])
    rec = agent.run_revision(ctx_for("D", Vp, report), prov, tools, model="scripted/mock")
    assert rec.proposal.outcome == "submitted" and rec.local_evals == 1 and rec.model_calls == 2
    assert rec.proposal.source == TORSO
    tool_msg = prov.calls[1][-1]["content"]
    assert "local evaluation 1 of 4" in tool_msg and "'P': 0.85" in tool_msg
    assert rec.transcript[0]["role"] == "system" and rec.transcript[-1]["role"] == "assistant"


def test_local_eval_cap_forces_a_submit(Vp, report, tools):
    prov = ScriptedProvider([reply(GEN0, "run_visible_eval")] * 6)
    rec = agent.run_revision(ctx_for("B", Vp, report), prov, tools, model="scripted/mock")
    assert rec.local_evals == 4 and rec.model_calls == 5
    assert rec.proposal.outcome == "forced_submit" and rec.proposal.source == GEN0
    assert "no local evaluations left" in prov.calls[4][-1]["content"]


def test_one_correction_is_allowed_then_failure_is_recorded(Vp, report, tools):
    prov = ScriptedProvider(["garbage", reply(GEN0, "submit")])
    rec = agent.run_revision(ctx_for("B", Vp, report), prov, tools, model="scripted/mock")
    assert rec.proposal.outcome == "submitted" and rec.model_calls == 2
    assert any(t.get("kind") == "correction" for t in rec.transcript)
    prov = ScriptedProvider(["garbage", "still garbage"])
    rec = agent.run_revision(ctx_for("B", Vp, report), prov, tools, model="scripted/mock")
    assert rec.proposal.outcome == "protocol_failure" and rec.proposal.source is None and rec.error


def test_provider_failure_is_recorded_not_raised(Vp, report, tools):
    rec = agent.run_revision(ctx_for("B", Vp, report), ScriptedProvider([]), tools, model="scripted/mock")
    assert rec.proposal.outcome == "provider_failure" and "exhausted" in rec.error


def test_arm_A_self_report_is_captured(Vp, report, tools):
    prov = ScriptedProvider([reply(GEN0, "submit"),
                             reply(GEN0, "submit", deploy=True, measured_visible_accuracy=0.95)])
    rec = agent.run_revision(ctx_for("A", Vp, report), prov, tools, model="scripted/mock", require_self_report=True)
    assert rec.proposal.outcome == "submitted" and rec.model_calls == 2
    assert rec.proposal.self_report == {"deploy": True, "measured_visible_accuracy": 0.95}


def test_scripted_proposal_flows_into_the_bundle(ds1, Vp, report, tools):
    prov = ScriptedProvider([reply(TORSO, "submit")])
    rec = agent.run_revision(ctx_for("D", Vp, report), prov, tools, model="scripted/mock")
    b = score_candidate(rec.proposal.source, ds1)
    assert b.sandbox_valid and b.envelope_inside


# --- provider request/response shapes ----------------------------------------------

def test_agent_request_has_no_tools_and_routes_system_to_instructions(Vp, report):
    body = build_agent_request(ctx_for("B", Vp, report).messages(), model="anthropic/claude-sonnet-5",
                               max_output_tokens=8000)
    assert set(body) == {"model", "input", "instructions", "max_output_tokens"}
    assert "tools" not in body and body["input"][0]["role"] == "user" and "Acceptance rule" in body["instructions"]
    body2 = build_agent_request([{"role": "user", "content": "x"}], model="m", max_output_tokens=10, temperature=0.7)
    assert body2["temperature"] == 0.7 and "instructions" not in body2


def test_response_text_and_cost_extraction():
    assert extract_text({"output_text": "hi"}) == "hi"
    assert extract_text({"output": [{"type": "message", "content": [{"type": "output_text", "text": "a"},
                                                                     {"type": "output_text", "text": "b"}]}]}) == "a\nb"
    assert extract_text({"choices": [{"message": {"content": "c"}}]}) == "c"
    assert extract_cost({"usage": {"cost": {"total_cost": 0.0123}}}) == 0.0123
    assert extract_cost({"usage": {}}) is None
