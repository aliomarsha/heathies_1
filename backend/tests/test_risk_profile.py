"""Long-term risk profile: de-identification, structured output, fallback, guard rails, isolation."""
import json
from types import SimpleNamespace

import pytest

from app import config
from app.risk import service
from app.risk.sanitize import PIIViolation, assert_clean, build_payload, identifiers_for, scrub_text
from app.risk.schema import RiskProfile
from conftest import BASE_ANSWERS, enrol, login, submit

PERSON = SimpleNamespace(code="HL-4321", display_name="Nadine Haddad", phone="+961 71 234 567")
ANSWERS = {**BASE_ANSWERS, "q_family_maternal": "yes", "q_alcohol": "weekly", "q_activity": "low",
           "q_governorate": "akkar", "q_barriers": ["transport"]}


def test_payload_is_allow_listed_and_generalised():
    p = build_payload(ANSWERS)
    blob = json.dumps(p)
    assert p["factors"]["age_band_years"] == "50-54"        # exact age never sent
    assert "akkar" not in blob.lower() and "transport" not in blob.lower()
    assert "governorate" not in blob and "barriers" not in blob
    assert_clean(p, identifiers_for(PERSON))                # no exception


def test_scrubber_and_gate():
    assert "[number]" in scrub_text("call me on +961 71 234 567")
    assert "[email]" in scrub_text("nadine@example.com")
    assert "[id]" in scrub_text("my code is HL-4321")
    with pytest.raises(PIIViolation):
        assert_clean({"factors": {"x": "Nadine said yes"}}, identifiers_for(PERSON))
    with pytest.raises(PIIViolation):
        assert_clean({"factors": {"x": "71234567"}}, identifiers_for(PERSON))


def test_identifier_collision_blocks_dispatch_instead_of_sending():
    odd = SimpleNamespace(code="HL-1", display_name="Never", phone=None)   # name equals an answer label
    r = service.generate_risk_profile({**ANSWERS, "q_alcohol": "never"}, odd, "en", backend="fixture")
    assert r.status == "blocked_pii" and r.profile is None


class FakeCompletions:
    def __init__(self, parse_result=None, parse_exc=None, text=None):
        self.parse_result, self.parse_exc, self.text = parse_result, parse_exc, text
        self.calls = []

    def parse(self, **kw):
        self.calls.append(("parse", kw))
        if self.parse_exc:
            raise self.parse_exc
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=self.parse_result, refusal=None))])

    def create(self, **kw):
        self.calls.append(("create", kw))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.text))])


def fake_client(monkeypatch, comp):
    monkeypatch.setattr(config, "DR7_API_KEY", "sk-dr7-test")
    monkeypatch.setattr(service, "_client", lambda *a: SimpleNamespace(chat=SimpleNamespace(completions=comp)))


GOOD = RiskProfile(estimated_risk_tier="Moderate",
                   non_modifiable_historical_factors=["Mother had breast cancer."],
                   modifiable_lifestyle_factors=["Weekly alcohol.", "Low activity."],
                   clinical_screening_recommendations=["Discuss genetic counselling.", "You do not have cancer.", "Risk is 12%."])


def test_dr7_uses_parse_with_strict_schema_and_deidentified_prompt(monkeypatch):
    comp = FakeCompletions(parse_result=GOOD)
    fake_client(monkeypatch, comp)
    r = service.generate_risk_profile(ANSWERS, PERSON, "en", backend="dr7")
    assert r.status == "ok" and r.mode == "parse" and r.profile.estimated_risk_tier == "Moderate"
    kind, kw = comp.calls[0]
    assert kind == "parse" and kw["response_format"] is RiskProfile and kw["model"] == config.DR7_MODEL
    sent = json.dumps(kw["messages"])
    for ident in ("Nadine", "Haddad", "HL-4321", "234 567", "akkar"):
        assert ident not in sent
    assert "Do NOT assess, predict or diagnose" in kw["messages"][0]["content"]
    # guard rail removed false reassurance and the percentage
    assert r.profile.clinical_screening_recommendations == ["Discuss genetic counselling."]
    assert len(r.dropped_items) == 2


def test_dr7_falls_back_to_validated_json_when_parse_unsupported(monkeypatch):
    class BadRequestError(Exception):
        pass
    text = "Here you go: " + json.dumps({"estimated_risk_tier": "Average", "non_modifiable_historical_factors": [],
                                         "modifiable_lifestyle_factors": ["Low activity."],
                                         "clinical_screening_recommendations": ["Screen per national guidance."]})
    comp = FakeCompletions(parse_exc=BadRequestError("response_format not supported"), text=text)
    fake_client(monkeypatch, comp)
    r = service.generate_risk_profile(ANSWERS, PERSON, "en", backend="dr7")
    assert r.status == "ok" and r.mode == "json_fallback" and [c[0] for c in comp.calls] == ["parse", "create"]


def test_dr7_bad_output_and_missing_key_fail_safely(monkeypatch):
    class BadRequestError(Exception):
        pass
    comp = FakeCompletions(parse_exc=BadRequestError("nope"), text='{"estimated_risk_tier": "Very high"}')
    fake_client(monkeypatch, comp)
    assert service.generate_risk_profile(ANSWERS, PERSON, "en", backend="dr7").status == "error"
    monkeypatch.setattr(config, "DR7_API_KEY", "")
    assert service.generate_risk_profile(ANSWERS, PERSON, "en", backend="dr7").status == "unavailable"


def test_profile_never_changes_care_pathway_and_respects_roles(client, monkeypatch):
    c = client
    monkeypatch.setattr(config, "RISK_BACKEND", "dr7")
    monkeypatch.setattr(config, "DR7_API_KEY", "")            # external model unreachable
    h, code = enrol(c)
    o = submit(c, h, q_age=33, q_symptoms=["lump"], q_symptom_duration="not_checked", q_menopause="pre", q_hormone_therapy=None)
    assert o["recommendation"]["action"] == "clinical_assessment"
    rp = c.get("/api/me/risk-profile", headers=h).json()["risk_profile"]
    assert rp["status"] == "unavailable" and "sent_payload" not in rp

    monkeypatch.setattr(config, "RISK_BACKEND", "fixture")
    gov = login(c, "programme")
    pid = next(r["id"] for r in c.get("/api/gov/worklist", headers=gov).json() if r["code"] == code)
    assert c.post(f"/api/gov/participants/{pid}/risk-profile", headers=gov).status_code == 200
    rec = c.get(f"/api/gov/participants/{pid}", headers=gov).json()
    assert rec["risk_profile"]["status"] == "ok" and rec["risk_profile"]["is_fixture"]
    assert code not in json.dumps(rec["risk_profile"]["sent_payload"])
    assert rec["recommendation"]["action"] == "clinical_assessment"     # unchanged
    me = c.get("/api/me/overview", headers=h).json()
    assert me["risk_profile"]["estimated_risk_tier"] in ("Low", "Average", "Moderate", "High")
    assert me["recommendation"]["action"] == "clinical_assessment"


def test_local_backend_uses_local_server_without_key(monkeypatch):
    comp = FakeCompletions(parse_result=GOOD)
    seen = {}

    def fake(name="dr7"):
        seen["target"] = service._target(name)
        return SimpleNamespace(chat=SimpleNamespace(completions=comp))

    monkeypatch.setattr(config, "DR7_API_KEY", "")
    monkeypatch.setattr(service, "_client", fake)
    r = service.generate_risk_profile(ANSWERS, PERSON, "en", backend="local")
    assert r.status == "ok" and r.model == config.LOCAL_LLM_MODEL
    assert seen["target"]["base_url"].startswith("http://localhost")
    assert comp.calls[0][1]["model"] == config.LOCAL_LLM_MODEL


def test_local_backend_unreachable_is_reported_not_crashing(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_LLM_BASE_URL", "http://127.0.0.1:9")   # nothing listens here
    monkeypatch.setattr(config, "LOCAL_LLM_TIMEOUT_SECONDS", 2)
    r = service.generate_risk_profile(ANSWERS, PERSON, "en", backend="local")
    assert r.status == "unavailable" and "running" in r.error
