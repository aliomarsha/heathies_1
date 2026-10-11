"""Participant-facing API. A participant can only ever reach her own records."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config
from ..auth import Actor, require
from ..db import get_db
from ..models import Appointment, HelpRequest, Participant
from ..services import care
from ..services.core import audit, now
from ..services.journey import (current_draft, journey, latest_finding, latest_pred, latest_rec, latest_submitted,
                                ser_appointment, ser_assessment, ser_finding, ser_participant_basic, ser_prediction,
                                ser_rec)
from ..services.outreach import cancel_events, open_task, suppress_all, tick
from ..services.risk_runner import create_pending, latest_for, run_in_background, ser_risk
from ..services.timeline import build_timeline

router = APIRouter(prefix="/api/me", tags=["participant"])
participant_only = require("participant")


def me_participant(actor: Actor, db: Session) -> Participant:
    p = db.get(Participant, actor.user.participant_id)
    if not p:
        raise HTTPException(404, "Participant record not found.")
    return p


def own_appointment(p: Participant, appt_id: int) -> Appointment:
    for a in p.appointments:
        if a.id == appt_id:
            return a
    raise HTTPException(404, "Appointment not found.")


def overview_payload(db: Session, p: Participant) -> dict[str, Any]:
    sub = latest_submitted(p)
    return {
        "participant": ser_participant_basic(p),
        "journey": journey(db, p),
        "draft": ser_assessment(current_draft(p), include_free_text=True),
        "latest_assessment": ser_assessment(sub, include_free_text=True),
        "prediction": ser_prediction(latest_pred(sub), staff=False),
        "recommendation": ser_rec(latest_rec(sub)),
        "appointments": [ser_appointment(a, "participant") for a in reversed(p.appointments)],
        "finding": ser_finding(latest_finding(p), "participant"),
        "risk_profile": ser_risk(latest_for(db, sub), staff=False),
        "timeline": build_timeline(p, "participant"),
        "help_requests": [{"id": h.id, "topic": h.topic, "status": h.status, "created_at": h.created_at.isoformat()}
                          for h in db.query(HelpRequest).filter(HelpRequest.participant_id == p.id).order_by(HelpRequest.id.desc())],
    }


@router.get("/overview")
def overview(actor: Actor = Depends(participant_only), db: Session = Depends(get_db)):
    return overview_payload(db, me_participant(actor, db))


class ContactUpdate(BaseModel):
    language: Optional[str] = Field(None, pattern="^(ar|en)$")
    channel: Optional[str] = Field(None, pattern="^(sms|call|none)$")
    time: Optional[str] = Field(None, pattern="^(morning|afternoon|evening|any)$")
    safe_to_leave_message: Optional[bool] = None
    discreet_messages: Optional[bool] = None
    opted_out: Optional[bool] = None


@router.put("/contact")
def update_contact(body: ContactUpdate, actor: Actor = Depends(participant_only), db: Session = Depends(get_db)):
    p = me_participant(actor, db)
    if body.language:
        p.language = body.language
    if body.channel:
        p.contact_channel = body.channel
    if body.time:
        p.contact_time = body.time
    if body.safe_to_leave_message is not None:
        p.safe_to_leave_message = body.safe_to_leave_message
    if body.discreet_messages is not None:
        p.discreet_messages = body.discreet_messages
    if body.opted_out is not None and body.opted_out != p.opted_out:
        p.opted_out = body.opted_out
        p.opted_out_at = now(db) if body.opted_out else None
        p.contact_state = "opted_out" if body.opted_out else "not_contacted"
        if body.opted_out:
            suppress_all(db, p.id)
    if p.contact_channel == "none":
        cancel_events(db, p.id, "Participant chose no contact")
    audit(db, p.code, "participant", "contact_preferences_updated", "participant", p.id, p.id,
          **body.model_dump(exclude_none=True))
    tick(db)
    db.commit()
    return overview_payload(db, p)


class HelpIn(BaseModel):
    topic: str = Field(..., pattern="^(survey|booking|transport|cost|worry|other)$")
    message: Optional[str] = Field(None, max_length=1000)


@router.post("/help")
def request_help(body: HelpIn, actor: Actor = Depends(participant_only), db: Session = Depends(get_db)):
    p = me_participant(actor, db)
    h = HelpRequest(participant_id=p.id, topic=body.topic, message=(body.message or "").strip() or None, created_at=now(db))
    db.add(h)
    db.flush()
    open_task(db, p.id, "help_request", f"Participant asked for help ({body.topic}). Contact using her preferences.",
              dedupe_key=f"help:{h.id}", due_days=1)
    audit(db, p.code, "participant", "help_requested", "help_request", h.id, p.id, topic=body.topic)
    db.commit()
    return overview_payload(db, p)


# ---------------------------------------------------------------- assessment -----
class DraftIn(BaseModel):
    answers: dict[str, Any] = {}
    free_text: Optional[str] = None
    current_step: Optional[int] = None


@router.get("/assessment")
def get_assessment(actor: Actor = Depends(participant_only), db: Session = Depends(get_db)):
    p = me_participant(actor, db)
    a = current_draft(p)
    if not a:
        if latest_submitted(p):
            return {"draft": None, "submitted": ser_assessment(latest_submitted(p), include_free_text=True)}
        a = care.new_assessment(db, p)
        audit(db, p.code, "participant", "assessment_started", "assessment", a.id, p.id)
        db.commit()
    return {"draft": ser_assessment(a, include_free_text=True)}


@router.post("/assessment/new")
def start_new(actor: Actor = Depends(participant_only), db: Session = Depends(get_db)):
    p = me_participant(actor, db)
    a = current_draft(p) or care.new_assessment(db, p)
    db.commit()
    return {"draft": ser_assessment(a, include_free_text=True)}


@router.put("/assessment")
def save(body: DraftIn, actor: Actor = Depends(participant_only), db: Session = Depends(get_db)):
    p = me_participant(actor, db)
    a = current_draft(p) or care.new_assessment(db, p)
    care.save_draft(db, a, body.answers, body.free_text, body.current_step)
    db.commit()
    return {"draft": ser_assessment(a, include_free_text=True)}


@router.post("/assessment/submit")
def submit(background: BackgroundTasks, actor: Actor = Depends(participant_only), db: Session = Depends(get_db)):
    p = me_participant(actor, db)
    a = current_draft(p)
    if not a:
        raise HTTPException(409, "There is no assessment in progress.")
    care.submit_assessment(db, a, p.code, "participant")
    # Educational long-term risk profile runs after the response, so it can never delay or
    # change the recommendation the participant has just received.
    rec = create_pending(db, a, p.code)
    db.commit()
    if rec or a.free_text:
        if config.INLINE_JOBS:
            run_in_background(rec.id if rec else None, a.id)   # serverless: finish before responding
            db.expire_all()   # re-read the results written by the job's own session
        else:
            background.add_task(run_in_background, rec.id if rec else None, a.id)
    return overview_payload(db, p)


@router.get("/risk-profile")
def my_risk_profile(actor: Actor = Depends(participant_only), db: Session = Depends(get_db)):
    p = me_participant(actor, db)
    return {"risk_profile": ser_risk(latest_for(db, latest_submitted(p)), staff=False)}


# ---------------------------------------------------------------- appointments ----
class ApptIn(BaseModel):
    hospital_id: int
    preferred_date: Optional[date] = None
    preferred_time: Optional[str] = Field(None, max_length=20)
    note: Optional[str] = Field(None, max_length=500)


@router.post("/appointments")
def create_appt(body: ApptIn, actor: Actor = Depends(participant_only), db: Session = Depends(get_db)):
    p = me_participant(actor, db)
    care.request_appointment(db, p, body.hospital_id, body.preferred_date, body.preferred_time, body.note, p.code, "participant")
    db.commit()
    return overview_payload(db, p)


class CancelIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=200)


@router.post("/appointments/{appt_id}/cancel")
def cancel_appt(appt_id: int, body: CancelIn, actor: Actor = Depends(participant_only), db: Session = Depends(get_db)):
    p = me_participant(actor, db)
    a = own_appointment(p, appt_id)
    if a.status not in ("requested", "confirmed", "reschedule_requested") or a.attendance != "unknown":
        raise HTTPException(409, "This appointment can no longer be cancelled.")
    a.status = "cancelled"
    a.cancel_reason = (body.reason or "").strip() or "Cancelled by participant"
    a.updated_at = now(db)
    audit(db, p.code, "participant", "appointment_cancelled", "appointment", a.id, p.id, reason=a.cancel_reason)
    tick(db)
    db.commit()
    return overview_payload(db, p)


class RescheduleIn(BaseModel):
    preferred_date: Optional[date] = None
    preferred_time: Optional[str] = Field(None, max_length=20)
    hospital_id: Optional[int] = None
    note: Optional[str] = Field(None, max_length=500)


@router.post("/appointments/{appt_id}/reschedule")
def reschedule(appt_id: int, body: RescheduleIn, actor: Actor = Depends(participant_only), db: Session = Depends(get_db)):
    p = me_participant(actor, db)
    a = own_appointment(p, appt_id)
    if a.status not in ("requested", "confirmed", "reschedule_requested") or a.attendance != "unknown":
        raise HTTPException(409, "This appointment can no longer be changed.")
    if body.hospital_id and body.hospital_id != a.hospital_id:
        # Different hospital: cancel this one and create a fresh request.
        a.status = "cancelled"
        a.cancel_reason = "Moved to another hospital by participant"
        a.updated_at = now(db)
        care.request_appointment(db, p, body.hospital_id, body.preferred_date, body.preferred_time, body.note,
                                 p.code, "participant", replaces=a, service=a.service)
    else:
        a.status = "reschedule_requested"
        a.preferred_date = body.preferred_date or a.preferred_date
        a.preferred_time = body.preferred_time or a.preferred_time
        if body.note:
            a.participant_note = body.note
        a.updated_at = now(db)
        audit(db, p.code, "participant", "reschedule_requested", "appointment", a.id, p.id,
              preferred_date=a.preferred_date, preferred_time=a.preferred_time)
        tick(db)
    db.commit()
    return overview_payload(db, p)


class SelfReportIn(BaseModel):
    attended: bool


@router.post("/appointments/{appt_id}/self-report")
def self_report(appt_id: int, body: SelfReportIn, actor: Actor = Depends(participant_only), db: Session = Depends(get_db)):
    """Recorded but NOT counted as verified attendance."""
    p = me_participant(actor, db)
    a = own_appointment(p, appt_id)
    if a.attendance_verified:
        raise HTTPException(409, "The hospital already verified this appointment.")
    if a.status != "confirmed":
        raise HTTPException(409, "Only confirmed appointments can be reported.")
    a.attendance_source = "self_report"
    a.participant_note = ((a.participant_note or "") + f"\n[Self-report: {'attended' if body.attended else 'did not attend'}]").strip()
    a.updated_at = now(db)
    open_task(db, p.id, "staff_review", "Participant self-reported attendance. Ask the hospital to verify.",
              dedupe_key=f"selfrep:{a.id}", due_days=2, owner_role="provider", appointment_id=a.id)
    audit(db, p.code, "participant", "attendance_self_reported", "appointment", a.id, p.id, attended=body.attended)
    db.commit()
    return overview_payload(db, p)
