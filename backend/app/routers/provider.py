"""Hospital/provider portal. A provider only sees appointments at their own hospital and the
participants who booked there."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Actor, require
from ..db import get_db
from ..models import Appointment, Participant
from ..services import care
from ..services.core import audit, now
from ..services.journey import (journey, latest_pred, latest_rec, latest_submitted, ser_appointment, ser_assessment,
                                ser_participant_basic, ser_prediction, ser_rec, ser_task)
from ..services.outreach import open_task, tick
from ..services.risk_runner import latest_for, ser_risk
from ..services.timeline import build_timeline

router = APIRouter(prefix="/api/provider", tags=["provider"])
provider_only = require("provider")


def my_appt(db: Session, actor: Actor, appt_id: int) -> Appointment:
    a = db.get(Appointment, appt_id)
    if not a or a.hospital_id != actor.user.hospital_id:
        raise HTTPException(404, "Appointment not found at your hospital.")
    return a


def appt_row(db: Session, a: Appointment) -> dict:
    p = a.participant
    sub = latest_submitted(p)
    return {
        **ser_appointment(a, "provider"),
        "participant": {
            "id": p.id,
            "code": p.code,
            "display_name": p.display_name,
            "age": (sub.answers or {}).get("q_age") if sub else None,
            "language": p.language,
            "contact_channel": p.contact_channel,
            "opted_out": p.opted_out,
        },
        "recommendation": ser_rec(latest_rec(sub)),
        "prediction": ser_prediction(latest_pred(sub), staff=True),
        "symptoms": (sub.answers or {}).get("q_symptoms") if sub else None,
        "has_free_text": bool(sub and sub.free_text),
    }


@router.get("/appointments")
def list_appts(actor: Actor = Depends(provider_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(Appointment).where(Appointment.hospital_id == actor.user.hospital_id).order_by(Appointment.id.desc()))
    return [appt_row(db, a) for a in rows]


@router.get("/participants/{pid}")
def participant_detail(pid: int, actor: Actor = Depends(provider_only), db: Session = Depends(get_db)):
    p = db.get(Participant, pid)
    if not p or not any(a.hospital_id == actor.user.hospital_id for a in p.appointments):
        raise HTTPException(404, "No appointment for this participant at your hospital.")
    sub = latest_submitted(p)
    audit(db, actor.name, "provider", "record_viewed", "participant", p.id, p.id)
    db.commit()
    return {
        "participant": ser_participant_basic(p),
        "journey": journey(db, p),
        "assessment": ser_assessment(sub, include_free_text=True),
        "prediction": ser_prediction(latest_pred(sub), staff=True),
        "recommendation": ser_rec(latest_rec(sub)),
        "risk_profile": ser_risk(latest_for(db, sub), staff=True),
        "appointments": [ser_appointment(a, "provider") for a in reversed(p.appointments) if a.hospital_id == actor.user.hospital_id],
        "tasks": [ser_task(t) for t in p.tasks if t.owner_role == "provider"],
        "timeline": build_timeline(p, "provider"),
    }


class ConfirmIn(BaseModel):
    date: date
    time: str = Field("09:00", pattern=r"^\d{2}:\d{2}$")


@router.post("/appointments/{appt_id}/confirm")
def confirm(appt_id: int, body: ConfirmIn, actor: Actor = Depends(provider_only), db: Session = Depends(get_db)):
    a = my_appt(db, actor, appt_id)
    care.confirm_appointment(db, a, care.combine(body.date, body.time), actor.name)
    db.commit()
    return appt_row(db, a)


class DeclineIn(BaseModel):
    reason: str = Field(..., min_length=2, max_length=200)


@router.post("/appointments/{appt_id}/decline")
def decline(appt_id: int, body: DeclineIn, actor: Actor = Depends(provider_only), db: Session = Depends(get_db)):
    a = my_appt(db, actor, appt_id)
    if a.status not in ("requested", "reschedule_requested"):
        raise HTTPException(409, "Only pending requests can be declined.")
    a.status = "declined"
    a.cancel_reason = body.reason
    a.updated_at = now(db)
    open_task(db, a.participant_id, "reschedule", f"Hospital could not take the request: {body.reason}. Help her choose another option.",
              dedupe_key=f"declined:{a.id}", due_days=1, appointment_id=a.id)
    audit(db, actor.name, "provider", "appointment_declined", "appointment", a.id, a.participant_id, reason=body.reason)
    tick(db)
    db.commit()
    return appt_row(db, a)


class AttendanceIn(BaseModel):
    attended: bool
    missed_reason: Optional[str] = None


@router.post("/appointments/{appt_id}/attendance")
def attendance(appt_id: int, body: AttendanceIn, actor: Actor = Depends(provider_only), db: Session = Depends(get_db)):
    a = my_appt(db, actor, appt_id)
    care.record_attendance(db, a, body.attended, body.missed_reason, actor.name)
    for t in a.participant.tasks:
        if t.status == "open" and t.dedupe_key == f"selfrep:{a.id}":
            t.status, t.closed_at, t.closed_by, t.resolution = "done", now(db), actor.name, "Hospital verified attendance"
    db.commit()
    return appt_row(db, a)


class FindingIn(BaseModel):
    state: str
    next_step: str
    next_review_date: Optional[date] = None
    clinician_name: Optional[str] = Field(None, max_length=120)
    clinical_note: Optional[str] = Field(None, max_length=2000)


@router.post("/appointments/{appt_id}/finding")
def finding(appt_id: int, body: FindingIn, actor: Actor = Depends(provider_only), db: Session = Depends(get_db)):
    a = my_appt(db, actor, appt_id)
    care.record_finding(db, a, body.state, body.next_step, body.next_review_date, body.clinician_name, body.clinical_note, actor.name)
    db.commit()
    return appt_row(db, a)
