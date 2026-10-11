"""Demo reset: rebuilds the database with FICTIONAL participants covering the handbook's demo cases.

Run:  python -m app.seed      (from /backend)   or use the "Reset demo" button in the app.

The seed replays each journey through the real service functions while moving the simulated
clock forward, so every timestamp, task, outreach event and audit entry is consistent.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from .config import DEMO_PASSWORD, HOSPITALS_FILE
from .db import Base, SessionLocal, engine
from .ml import backends
from .models import Hospital, Participant, User
from .policy.action_policy import load_policy
from . import config
from .services import care
from .services.risk_runner import complete, create_pending, triage_assessment
from .services.core import audit, hash_password, now, set_setting
from .services.outreach import load_templates, suppress_all, tick
from .survey import load_survey

DEMO_PIN = "1234"

BASE_ANSWERS = {
    "q_age": 52,
    "q_governorate": "beirut",
    "q_symptoms": ["none"],
    "q_personal_history": "no",
    "q_family_maternal": "no",
    "q_family_paternal": "no",
    "q_surveillance_plan": "no",
    "q_menarche": "12_13",
    "q_menopause": "post",
    "q_hormone_therapy": "never",
    "q_first_birth": "under_30",
    "q_last_mammogram": "over_2y",
    "q_unresolved": "no",
    "q_barriers": ["none"],
}


def clear_caches() -> None:
    load_survey.cache_clear()
    load_policy.cache_clear()
    load_templates.cache_clear()
    backends.reset_caches()


def _hospitals(db: Session) -> dict[str, Hospital]:
    with open(HOSPITALS_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    out = {}
    for h in data["hospitals"]:
        row = Hospital(
            slug=h["slug"], name_en=h["name_en"], name_ar=h["name_ar"], sector=h["sector"],
            governorate=h["governorate"], district=h.get("district"), services=h["services"],
            phone=h.get("phone"), cost_status=h.get("cost_status", "unknown"),
            cost_note_en=h.get("cost_note_en"), cost_note_ar=h.get("cost_note_ar"),
            info_verified=h.get("info_verified", False),
            source_url=h.get("source_url", "https://www.moph.gov.lb/en/Pages/11/87130/national-breast-cancer-awareness-campaign-2026"),
            demo_slots=h.get("demo_slots", []), is_demo_partner=h.get("is_demo_partner", False),
        )
        db.add(row)
        out[h["slug"]] = row
    db.flush()
    return out


def _staff(db: Session, hospitals: dict[str, Hospital]) -> None:
    pw = hash_password(DEMO_PASSWORD)
    db.add(User(username="programme", password_hash=pw, role="government", display_name="Programme officer (demo)"))
    db.add(User(username="coordinator", password_hash=pw, role="government", display_name="Outreach coordinator (demo)"))
    for slug, h in hospitals.items():
        db.add(User(username=f"{slug}.desk", password_hash=pw, role="provider",
                    display_name=f"Imaging desk – {h.name_en} (demo)", hospital_id=h.id))
    db.flush()


def _participant(db: Session, code: str, name: str, *, lang: str = "ar", gov: str = "beirut", source: str = "direct",
                 channel: str = "sms", phone: Optional[str] = None) -> Participant:
    ts = now(db)
    p = Participant(code=code, display_name=name, phone=phone or f"+961 70 000 {code[-3:]}", language=lang, governorate=gov,
                    source=source, enrolled_at=ts, consent_given=source == "direct", consent_version="consent-v0.1-demo" if source == "direct" else None,
                    consent_at=ts if source == "direct" else None, contact_channel=channel, contact_time="any",
                    safe_to_leave_message=False, discreet_messages=True, is_demo=True)
    db.add(p)
    db.flush()
    db.add(User(username=code.lower(), password_hash=hash_password(DEMO_PIN), role="participant", display_name=name, participant_id=p.id))
    audit(db, code, "participant", "enrolled_with_consent" if source == "direct" else "invited_by_campaign", "participant", p.id, p.id)
    db.flush()
    return p


def _assess(db: Session, p: Participant, overrides: dict[str, Any], *, submit: bool = True, free_text: Optional[str] = None,
            step: int = 0, fail_model: bool = False) -> None:
    a = care.new_assessment(db, p)
    answers = {**BASE_ANSWERS, "q_governorate": p.governorate, **overrides}
    answers = {k: v for k, v in answers.items() if v is not None}
    care.save_draft(db, a, answers, free_text, step)
    if submit:
        if fail_model:
            set_setting(db, "demo_model_failure", "1")
        care.submit_assessment(db, a, p.code, "participant")
        set_setting(db, "demo_model_failure", "0")
        # seeded people get a demo (fixture) risk profile; staff can regenerate with the live backend
        rec = create_pending(db, a, "seed", backend="hybrid" if config.RISK_BACKEND != "off" else "off")
        if rec:
            complete(db, rec)
        triage_assessment(db, a, decision_backend="rules")
    db.flush()


def _advance(db: Session, days: float) -> None:
    from .services.core import advance_clock
    advance_clock(db, days)
    tick(db)


def reset_demo() -> dict[str, Any]:
    engine.dispose()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    clear_caches()
    db = SessionLocal()
    try:
        set_setting(db, "sim_offset_days", "-14")
        set_setting(db, "demo_model_failure", "0")
        db.flush()

        H = _hospitals(db)
        _staff(db, H)
        pw_note = {"staff_password": DEMO_PASSWORD, "participant_pin": DEMO_PIN}

        # ---- day -14 ---------------------------------------------------------------
        layla = _participant(db, "HL-1006", "Layla H.", gov="beirut")
        _assess(db, layla, {"q_age": 58, "q_last_mammogram": "1_2y"})
        care.request_appointment(db, layla, H["rhuh"].id, None, "morning", None, layla.code, "participant")
        zeina = _participant(db, "HL-1007", "Zeina B.", gov="north", source="campaign_invite")
        _advance(db, 1)

        # ---- day -13 ---------------------------------------------------------------
        hala = _participant(db, "HL-1004", "Hala S.", gov="mount_lebanon", lang="en")
        _assess(db, hala, {"q_age": 47, "q_governorate": "mount_lebanon", "q_family_maternal": "yes", "q_family_paternal": "yes",
                           "q_menopause": "pre", "q_hormone_therapy": None, "q_last_mammogram": "never", "q_barriers": ["worry"]})
        care.request_appointment(db, hala, H["baabda"].id, None, "morning", None, hala.code, "participant")
        appt_layla = layla.appointments[-1]
        care.confirm_appointment(db, appt_layla, care.combine((now(db) + timedelta(days=4)).date(), "09:00"), "rhuh.desk")
        _advance(db, 1)

        # ---- day -12 ---------------------------------------------------------------
        samira = _participant(db, "HL-1003", "Samira D.", gov="akkar")
        _assess(db, samira, {"q_age": 61, "q_governorate": "akkar", "q_barriers": ["transport", "cost"]})
        # She initially chose a Beirut hospital
        care.request_appointment(db, samira, H["rhuh"].id, None, "morning", "Can come with my son on weekdays", samira.code, "participant")
        care.confirm_appointment(db, hala.appointments[-1], care.combine((now(db) + timedelta(days=4)).date(), "10:30"), "baabda.desk")
        care.confirm_appointment(db, samira.appointments[-1], care.combine((now(db) + timedelta(days=5)).date(), "11:00"), "rhuh.desk")
        _advance(db, 1)

        # ---- day -11: campaign invite with no response -> reminders -> callback ----
        nour = _participant(db, "HL-1005", "Nour A.", gov="bekaa", source="campaign_invite")
        # Zeina received the invitation, then asked the programme team not to contact her again
        zeina.opted_out = True
        zeina.opted_out_at = now(db)
        zeina.contact_state = "opted_out"
        suppress_all(db, zeina.id)
        audit(db, "coordinator", "government", "opt_out_recorded", "participant", zeina.id, zeina.id, note="Asked by phone not to be contacted")
        _advance(db, 2)

        # ---- day -9 ---------------------------------------------------------------
        _advance(db, 0.2)
        care.record_attendance(db, appt_layla, True, None, "rhuh.desk")
        care.record_finding(db, appt_layla, "negative_benign", "routine_review", (now(db) + timedelta(days=365)).date(),
                            "Dr. R. Haddad (fictional)", "BI-RADS 1 (fictional demo note). Routine review in 12 months per clinician plan.", "rhuh.desk")
        hala_appt = hala.appointments[-1]
        care.record_attendance(db, hala_appt, True, None, "baabda.desk")
        care.record_finding(db, hala_appt, "incomplete_suspicious", "further_imaging", (now(db) + timedelta(days=10)).date(),
                            "Dr. N. Khoury (fictional)", "Additional views and ultrasound requested (fictional demo note).", "baabda.desk")
        _advance(db, 1.8)

        # ---- day -7 ---------------------------------------------------------------
        care.record_attendance(db, samira.appointments[-1], False, "transport", "rhuh.desk")
        dalal = _participant(db, "HL-1009", "Dalal M.", gov="south")
        _assess(db, dalal, {"q_age": 55, "q_governorate": "south", "q_last_mammogram": "never"}, fail_model=True)
        _advance(db, 3)

        # ---- day -4 ---------------------------------------------------------------
        rania = _participant(db, "HL-1008", "Rania F.", gov="nabatieh", channel="call")
        _assess(db, rania, {"q_age": "unknown", "q_governorate": "nabatieh", "q_symptoms": ["unknown"], "q_family_maternal": "unknown",
                            "q_last_mammogram": "unknown", "q_barriers": ["where"]},
                free_text="I am not sure about some answers, I would prefer someone calls me.")
        fatima = _participant(db, "HL-1011", "Fatima R.", gov="beirut", lang="en")
        _assess(db, fatima, {"q_age": 49, "q_menopause": "peri", "q_hormone_therapy": "past", "q_barriers": ["time"]})
        care.request_appointment(db, fatima, H["rhuh"].id, None, "afternoon", None, fatima.code, "participant")
        _advance(db, 1)

        # ---- day -3 ---------------------------------------------------------------
        care.confirm_appointment(db, fatima.appointments[-1], care.combine((now(db) + timedelta(days=5)).date(), "13:00"), "rhuh.desk")
        lina = _participant(db, "HL-1012", "Lina G.", gov="mount_lebanon")
        _assess(db, lina, {"q_age": 45, "q_governorate": "mount_lebanon", "q_menopause": "pre", "q_hormone_therapy": None,
                           "q_last_mammogram": "under_1y"})
        _advance(db, 2)

        # ---- day -1 ---------------------------------------------------------------
        maya = _participant(db, "HL-1002", "Maya T.", gov="beirut", lang="en")
        _assess(db, maya, {"q_age": 34, "q_symptoms": ["lump"], "q_symptom_duration": "not_checked", "q_menopause": "pre",
                           "q_hormone_therapy": None, "q_first_birth": "no_births", "q_last_mammogram": "never", "q_barriers": ["worry"]},
                free_text="I found it two weeks ago and I am scared to go alone.")
        mona = _participant(db, "HL-1010", "Mona K.", gov="baalbek_hermel")
        _assess(db, mona, {"q_age": 50, "q_governorate": "baalbek_hermel", "q_symptoms": ["none"]}, submit=False, step=2)
        # trim Mona's draft to the first sections so "resume" is visible
        d = mona.assessments[-1]
        d.answers = {k: v for k, v in d.answers.items() if k in ("q_age", "q_governorate", "q_symptoms")}
        _advance(db, 0.7)

        # ---- today ----------------------------------------------------------------
        rima = _participant(db, "HL-1001", "Rima N.", gov="beirut")
        _assess(db, rima, {"q_age": 52})
        care.request_appointment(db, rima, H["rhuh"].id, (now(db) + timedelta(days=6)).date(), "morning", None, rima.code, "participant")


        # align the simulated clock with real time
        set_setting(db, "sim_offset_days", "0")
        tick(db)
        db.commit()
        return {"ok": True, "participants": db.query(Participant).count(), **pw_note}
    finally:
        db.close()


if __name__ == "__main__":
    print(reset_demo())
