"""Hybrid pipeline: rules floor -> Jev tier decision -> MedGemma wording -> cache; plus note triage."""
import json
from types import SimpleNamespace

import httpx
import pytest

from app import config
from app.decisions import jev
from app.decisions import service as dec
from app.risk import service
from app.risk.writer import RiskWording
from conftest import BASE_ANSWERS, enrol, login

PERSON = SimpleNamespace(code="HL-4321", display_name="Nadine Haddad", phone="+961 71 234 567")
ANS = {**BASE_ANSWERS, "q_family_maternal": "yes", "q_activity": "low"}   # rules tier: Moderate


def run(**kw):
    return service.generate_risk_profile(ANS, PERSON, "en", backend="hybrid", **kw)


def fake_jev(monkeypatch, answer):
    calls = []

    def _call(state, questions):
        calls.append((state, questions))
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(jev, "call", _call)
    return calls


def test_rules_only_mode_needs_no_network():
    r = run(decision_backend="rules", writer="templates")
    assert r.status == "ok" and r.profile.estimated_risk_tier == "Moderate"
    assert r.mode == "tier:rules|text:templates" and not r.is_fixture


def test_jev_can_raise_the_tier(monkeypatch):
    calls = fake_jev(monkeypatch, {"risk_tier": {"value": "High", "confidence": 0.9}})
    r = run(decision_backend="jev", writer="templates")
    assert r.profile.estimated_risk_tier == "High" and r.decision["source"] == "jev"
    state = calls[0][0]
    for ident in ("Nadine", "HL-4321", "234"):
        assert ident not in state                    # Jev only sees the de-identified payload


def test_jev_can_never_go_below_the_rules_floor(monkeypatch):
    fake_jev(monkeypatch, {"risk_tier": {"value": "Low", "confidence": 0.99}})
    r = run(decision_backend="jev", writer="templates")
    assert r.profile.estimated_risk_tier == "Moderate" and r.decision["source"] == "rules_floor"


def test_low_confidence_or_outage_falls_back_to_rules(monkeypatch):
    fake_jev(monkeypatch, {"risk_tier": {"value": "High", "confidence": 0.2}})
    assert run(decision_backend="jev", writer="templates").decision["source"] == "rules"
    fake_jev(monkeypatch, jev.JevUnavailable("down"))
    r = run(decision_backend="jev", writer="templates")
    assert r.status == "ok" and r.decision["source"] == "rules" and any("Jev fallback" in n for n in r.notes)


def test_jev_request_shape_and_response_parsing(monkeypatch):
    seen = {}

    def post(url, json=None, timeout=None, headers=None):
        seen.update(url=url, body=json, headers=headers)
        return httpx.Response(200, json={"answers": {"risk_tier": {"choice": "Moderate",
                              "probabilities": {"Moderate": 0.7, "High": 0.3}, "confidence": 0.8}}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(config, "JEV_API_KEY", "jev-test")
    monkeypatch.setattr(httpx, "post", post)
    out = jev.call("state", dec.TIER_QUESTION)
    assert out["risk_tier"]["value"] == "Moderate" and out["risk_tier"]["confidence"] == 0.8
    assert seen["url"] == config.JEV_URL and seen["headers"]["Authorization"] == "Bearer jev-test"
    q = seen["body"]["questions"]["risk_tier"]
    assert seen["body"]["model"] == "jev-latest" and q["type"] == "choice" and set(q["criteria"]) == set(dec.TIERS)


@pytest.mark.parametrize("resp", [
    {"risk_tier": {"value": "High"}},
    {"results": [{"id": "risk_tier", "choice": "High", "confidence": 0.7}]},
    {"answers": {"risk_tier": {"probabilities": {"High": 0.6, "Low": 0.4}}}},
])
def test_normalise_accepts_likely_shapes(resp):
    assert jev.normalise(resp, dec.TIER_QUESTION)["risk_tier"]["value"] == "High"


def test_normalise_rejects_bad_answers():
    with pytest.raises(jev.JevFormatError):
        jev.normalise({"risk_tier": {"value": "Very high"}}, dec.TIER_QUESTION)
    with pytest.raises(jev.JevFormatError):
        jev.normalise({"something": 1}, dec.TIER_QUESTION)


class Comp:
    def __init__(self, parsed=None, exc=None):
        self.parsed, self.exc, self.calls = parsed, exc, []

    def parse(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=self.parsed, refusal=None))])


def writer(monkeypatch, comp):
    monkeypatch.setattr(service, "_client", lambda *a: SimpleNamespace(chat=SimpleNamespace(completions=comp)))


def test_medgemma_writes_wording_but_cannot_change_tier_or_add_factors(monkeypatch):
    base = run(decision_backend="rules", writer="templates").profile
    n_hist, n_life = len(base.non_modifiable_historical_factors), len(base.modifiable_lifestyle_factors)
    comp = Comp(RiskWording(
        non_modifiable_historical_factors=[f"Rewritten history {i}" for i in range(n_hist)],
        modifiable_lifestyle_factors=[f"Rewritten habit {i}" for i in range(n_life + 2)],      # tries to add factors
        clinical_screening_recommendations=["You do not have cancer."] + ["Talk to a clinician."] * (len(base.clinical_screening_recommendations) - 1)))
    writer(monkeypatch, comp)
    r = run(decision_backend="rules", writer="local")
    assert r.profile.estimated_risk_tier == "Moderate"
    assert r.profile.non_modifiable_historical_factors[0] == "Rewritten history 0"
    assert r.profile.modifiable_lifestyle_factors == base.modifiable_lifestyle_factors      # rejected section
    assert "You do not have cancer." not in r.profile.clinical_screening_recommendations     # guard rail
    assert comp.calls[0]["model"] == config.LOCAL_LLM_MODEL and comp.calls[0]["response_format"] is RiskWording
    assert "FIXED" in comp.calls[0]["messages"][0]["content"] and "Moderate" in comp.calls[0]["messages"][1]["content"]


def test_writer_outage_uses_templates(monkeypatch):
    class APIConnectionError(Exception):
        pass
    writer(monkeypatch, Comp(exc=APIConnectionError("refused")))
    r = run(decision_backend="rules", writer="local")
    assert r.status == "ok" and r.decision["text_by"] == "templates" and any("Ollama" in n for n in r.notes)


def test_cache_reuses_identical_profiles(client, monkeypatch):
    monkeypatch.setattr(config, "RISK_BACKEND", "hybrid")
    monkeypatch.setattr(config, "DECISION_BACKEND", "jev")
    calls = fake_jev(monkeypatch, {"risk_tier": {"value": "High", "confidence": 0.9}})
    c = client
    for _ in range(3):
        h, _ = enrol(c)
        c.get("/api/me/assessment", headers=h)
        c.put("/api/me/assessment", headers=h, json={"answers": ANS})
        c.post("/api/me/assessment/submit", headers=h)
    assert len(calls) == 1                                   # 3 people, 1 Jev call
    rp = c.get("/api/me/risk-profile", headers=h).json()["risk_profile"]
    assert rp["status"] == "ok" and rp["estimated_risk_tier"] == "High"


def test_note_triage_only_adds_review(client, monkeypatch):
    c = client
    gov = login(c, "programme")
    h, code = enrol(c)
    c.get("/api/me/assessment", headers=h)
    c.put("/api/me/assessment", headers=h, json={"answers": BASE_ANSWERS,
          "free_text": "I found a small lump last week and I am scared to go alone"})
    o = c.post("/api/me/assessment/submit", headers=h).json()
    assert o["recommendation"]["action"] == "routine_screening"            # policy untouched
    pid = next(r["id"] for r in c.get("/api/gov/worklist", headers=gov).json() if r["code"] == code)
    rec = c.get(f"/api/gov/participants/{pid}", headers=gov).json()
    assert rec["note_triage"]["flag_breast_change"] is True
    assert any("may describe a breast change" in t["note"] for t in rec["tasks"] if t["status"] == "open")


def test_jev_triage_can_add_but_not_remove_flag(monkeypatch):
    fake_jev(monkeypatch, {"mentions_breast_change": {"probability": 0.05}, "barrier": {"value": "none"}})
    assert dec.triage_note("there is a lump", "jev").flag_breast_change is True          # rules hit stands
    fake_jev(monkeypatch, {"mentions_breast_change": {"probability": 0.8}, "barrier": {"value": "transport"}})
    d = dec.triage_note("something feels different on one side", "jev")
    assert d.flag_breast_change is True and d.barrier == "transport" and d.source == "jev+rules"


def test_note_is_scrubbed_before_triage():
    out = dec.scrub_note("I am Nadine Haddad, call +961 71 234 567", ["Nadine Haddad", "Nadine", "Haddad"])
    assert "Nadine" not in out and "234" not in out
