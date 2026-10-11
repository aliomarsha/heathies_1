"""Care-journey operations shared by the participant, provider and programme routers."""
from __future__ import annotations

import secrets
from datetime import date, datetime, time
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import config
from ..ml.contract import ModelRequest
from ..ml.features import build_features
from ..ml.service import run_model
from ..models import Appointment, Assessment, Finding, Hospital, OutcomeFeedback, Participant, Prediction, Recommendation
from ..policy.action_policy import decide
from ..survey import clean_answers, load_survey, missing_required, strip_hidden
from .core import audit, get_setting, now
from .outreach import cancel_events, open_task, tick

FINDING_STATES = {"pending", "negative_benign", "incomplete_suspicious", "biopsy_confirmed"}
NEXT_STEPS = {
    "pending": {"await_result"},
    "negative_benign": {"routine_review", "clinician_plan"},
    "incomplete_suspicious": {"further_imaging", "biopsy", "specialist_referral", "clinician_plan"},
    "biopsy_confirmed": {"specialist_referral", "clinician_plan"},
}
MISSED_REASONS = {"transport", "cost", "worry", "time", "illness", "forgot", "unreachable", "other", "unknown"}


def new_assessment(db: Session, p: Participant) -> Assessment:
    ts = now(db)
    a = Assessment(
        public_id="AS-" + secrets.token_hex(5).upper(),
        participant_id=p.id,
        schema_version=load_survey()["schema_version"],
        status="draft",
        answers={},
        current_step=0,
        created_at=ts,
        updated_at=ts,
    )
    p.assessments.append(a)
    db.flush()
    return a


def save_draft(db: Session, a: Assessment, answers: dict[str, Any], free_text: Optional[str], step: Optional[int]) -> Assessment:
    if a.status != "draft":
        raise HTTPException(409, "This assessment was already submitted. Start a new one to change answers.")
    merged = {**(a.answers or {}), **clean_answers(answers)}
    # explicit removals (answer cleared)
    for k, v in (answers or {}).items():
        if v is None:
            merged.pop(k, None)
    a.answers = strip_hidden(merged)
    if free_text is not None:
        a.free_text = free_text.strip()[:2000] or None
    if step is not None:
        a.current_step = max(0, int(step))
    a.updated_at = now(db)
    return a


def submit_assessment(db: Session, a: Assessment, actor: str, role: str) -> tuple[Prediction, Recommendation]:
    if a.status != "draft":
        raise HTTPException(409, "Already submitted.")
    answers = strip_hidden(a.answers or {})
    missing = missing_required(answers)
    if missing:
        raise HTTPException(422, {"message": "Some questions still need an answer.", "missing": missing})
    ts = now(db)
    a.answers = answers
    a.status = "submitted"
    a.submitted_at = ts
    a.updated_at = ts

    features, unknown = build_features(answers)
    req = ModelRequest(
        contract_version=config.CONTRACT_VERSION,
        assessment_id=a.public_id,
        schema_version=a.schema_version,
        submitted_at=ts.isoformat(),
        features=features,
        unknown_features=unknown,
    ).to_dict()
    force_fail = get_setting(db, "demo_model_failure", "0") == "1"
    result = run_model(req, force_failure=force_fail)

    pred = Prediction(
        assessment_id=a.id,
        status=result.status,
        backend=result.backend,
        is_fixture=result.is_fixture,
        model_version=result.model_version,
        target_definition=result.target_definition,
        score=result.score,
        band=result.band,
        review_flag=result.review_flag,
        reason_codes=result.reason_codes,
        threshold_version=result.threshold_version,
        request_payload=req,
        raw_response=result.raw_response,
        error_message=result.error_message,
        created_at=ts,
    )
    a.predictions.append(pred)
    db.flush()

    d = decide(answers, result)
    rec = Recommendation(
        assessment_id=a.id,
        prediction_id=pred.id,
        action=d["action"],
        service=d["service"],
        policy_version=d["policy_version"],
        booking_eligible=d["booking_eligible"],
        clinician_review=d["clinician_review"],
        priority=d["priority"],
        reason_codes=d["reason_codes"],
        created_at=ts,
    )
    a.recommendations.append(rec)
    db.flush()

    p = a.participant
    # Tasks for staff
    if result.status != "ok":
        open_task(db, p.id, "staff_review", f"Model result unavailable ({result.status}). Review the assessment manually; "
                  "do not treat as low risk.", dedupe_key=f"modelfail:{a.id}", due_days=1)
    if d["action"] == "clarification":
        open_task(db, p.id, "clarification", "Critical information unknown: " + ", ".join(d["unknown_critical"]) +
                  ". Call to clarify.", dedupe_key=f"clarify:{a.id}", due_days=2)
    if d["action"] == "clinical_assessment":
        open_task(db, p.id, "clinical_follow_up", "Concerning symptom or unresolved investigation reported. Make sure a "
                  "clinical assessment is booked promptly.", dedupe_key=f"clin:{a.id}", due_days=1)
    if a.free_text:
        open_task(db, p.id, "staff_review", "Participant left a free-text note for the care team. Read it in the record.",
                  dedupe_key=f"freetext:{a.id}", due_days=2)

    cancel_events(db, p.id, "Assessment completed", templates=("invitation", "assessment_reminder"))
    audit(db, actor, role, "assessment_submitted", "assessment", a.id, p.id,
          model_status=result.status, band=result.band, recommended_action=d["action"])
    tick(db)
    return pred, rec


def request_appointment(db: Session, p: Participant, hospital_id: int, preferred_date: Optional[date],
                        preferred_time: Optional[str], note: Optional[str], actor: str, role: str,
                        replaces: Optional[Appointment] = None, service: Optional[str] = None) -> Appointment:
    sub = [a for a in p.assessments if a.status == "submitted"]
    if not sub:
        raise HTTPException(409, "Complete the assessment before requesting an appointment.")
    rec = sub[-1].recommendations[-1] if sub[-1].recommendations else None
    if not rec or (not rec.booking_eligible and role == "participant"):
        raise HTTPException(409, "Your next step does not need a booking yet. Request help and the team will contact you.")
    h = db.get(Hospital, hospital_id)
    if not h:
        raise HTTPException(404, "Hospital not found.")
    svc = service or rec.service
    if svc == "none" or svc == "clarification_call":
        svc = "screening_mammogram"
    if svc not in h.services:
        raise HTTPException(409, "This hospital is not listed for that service. Choose another hospital.")
    live = [a for a in p.appointments if a.status in ("requested", "confirmed", "reschedule_requested") and a.attendance == "unknown"]
    if live and not replaces:
        raise HTTPException(409, "You already have an active appointment. Reschedule or cancel it first.")
    ts = now(db)
    appt = Appointment(
        participant_id=p.id,
        hospital_id=h.id,
        recommendation_id=rec.id,
        service=svc,
        status="requested",
        preferred_date=preferred_date,
        preferred_time=preferred_time,
        participant_note=(note or "").strip()[:500] or None,
        replaces_id=replaces.id if replaces else None,
        created_at=ts,
        updated_at=ts,
    )
    p.appointments.append(appt)
    db.flush()
    audit(db, actor, role, "appointment_requested", "appointment", appt.id, p.id, hospital=h.slug, service=svc)
    tick(db)
    return appt


def confirm_appointment(db: Session, appt: Appointment, when: datetime, actor: str) -> None:
    if appt.status not in ("requested", "reschedule_requested", "confirmed"):
        raise HTTPException(409, f"Cannot confirm an appointment that is {appt.status}.")
    if appt.attendance != "unknown":
        raise HTTPException(409, "Attendance was already recorded.")
    appt.status = "confirmed"
    appt.confirmed_at = when
    appt.confirmed_by = actor
    appt.confirmed_on = now(db)
    appt.updated_at = now(db)
    audit(db, actor, "provider", "appointment_confirmed", "appointment", appt.id, appt.participant_id, when=when)
    tick(db)


def record_attendance(db: Session, appt: Appointment, attended: bool, missed_reason: Optional[str], actor: str) -> None:
    if appt.status != "confirmed":
        raise HTTPException(409, "Only confirmed appointments can have attendance recorded.")
    ts = now(db)
    appt.attendance = "attended" if attended else "missed"
    appt.attendance_source = "provider"
    appt.attendance_verified = True
    appt.attendance_by = actor
    appt.attendance_on = ts
    appt.updated_at = ts
    if not attended:
        reason = missed_reason if missed_reason in MISSED_REASONS else "unknown"
        appt.missed_reason = reason
        # A missed appointment is not refusal: open a barrier-support task for the programme team.
        open_task(db, appt.participant_id, "barrier_support",
                  f"Missed appointment (reason recorded: {reason}). Contact to resolve the barrier and rebook.",
                  dedupe_key=f"missed:{appt.id}", due_days=1, appointment_id=appt.id)
    audit(db, actor, "provider", "attendance_recorded", "appointment", appt.id, appt.participant_id,
          attendance=appt.attendance, missed_reason=appt.missed_reason)
    tick(db)


def record_finding(db: Session, appt: Appointment, state: str, next_step: str, next_review_date: Optional[date],
                   clinician_name: Optional[str], clinical_note: Optional[str], actor: str) -> Finding:
    if appt.attendance != "attended" or not appt.attendance_verified:
        raise HTTPException(409, "Record verified attendance before entering a finding.")
    if state not in FINDING_STATES:
        raise HTTPException(422, "Unknown finding state.")
    if next_step not in NEXT_STEPS[state]:
        raise HTTPException(422, f"Next step '{next_step}' is not valid for '{state}'.")
    if next_review_date and state != "negative_benign":
        # dates for other states are follow-up dates set by the clinician; still allowed
        pass
    if state == "negative_benign" and next_step == "routine_review" and not next_review_date:
        raise HTTPException(422, "Enter the clinician-approved next review date.")
    if state != "pending" and not (clinician_name or "").strip():
        raise HTTPException(422, "Enter the name of the clinician who approved this next step.")
    ts = now(db)
    f = Finding(
        appointment_id=appt.id,
        participant_id=appt.participant_id,
        state=state,
        next_step=next_step,
        next_review_date=next_review_date,
        clinician_name=(clinician_name or "").strip() or None,
        clinical_note=(clinical_note or "").strip() or None,
        verification_source="provider_record",
        entered_by=actor,
        created_at=ts,
    )
    appt.findings.append(f)
    db.flush()
    p = appt.participant
    # Tasks: open follow-up stays open until a later finding resolves it.
    if state in ("incomplete_suspicious", "biopsy_confirmed"):
        open_task(db, p.id, "clinical_follow_up",
                  "Further assessment required after verified attendance. Keep follow-up open until the clinician records the outcome.",
                  dedupe_key=f"finding:{f.id}", due_days=7, appointment_id=appt.id, owner_role="provider")
    else:
        for t in p.tasks:
            if t.status == "open" and t.kind == "clinical_follow_up" and t.appointment_id == appt.id:
                t.status = "done"
                t.closed_at = ts
                t.closed_by = actor
                t.resolution = f"Finding recorded: {state}"
    if state != "pending":
        appt.status = "closed" if state == "negative_benign" else appt.status

    # Future-learning record (offline only). Not a usable label until reviewed.
    sub = [a for a in p.assessments if a.status == "submitted"]
    if sub:
        a = sub[-1]
        pr = a.predictions[-1] if a.predictions else None
        rec = a.recommendations[-1] if a.recommendations else None
        db.add(OutcomeFeedback(
            participant_id=p.id,
            assessment_id=a.id,
            prediction_id=pr.id if pr else None,
            finding_id=f.id,
            assessment_snapshot={"answers": a.answers, "schema_version": a.schema_version},
            prediction_time=pr.created_at if pr else None,
            model_version=pr.model_version if pr else None,
            score=pr.score if pr else None,
            recommended_action=rec.action if rec else None,
            verification_source="provider_record",
            outcome_state=state,
            outcome_date=ts,
            follow_up_period_note="Imaging result only - not automatically a cancer-negative label. Requires label review against model target.",
            label_usable=False,
        ))
    audit(db, actor, "provider", "finding_recorded", "finding", f.id, p.id, state=state, next_step=next_step,
          next_review_date=next_review_date, clinician=clinician_name)
    tick(db)
    return f


def combine(d: date, t: str) -> datetime:
    hh, mm = (t or "09:00").split(":")[:2]
    return datetime.combine(d, time(int(hh), int(mm)))
