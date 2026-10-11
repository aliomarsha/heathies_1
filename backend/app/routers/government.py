"""Programme / government dashboard API: worklist, metrics, tasks, outreach simulation.
Programme staff see care states and finding categories, but not clinicians' notes."""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..auth import Actor, require
from ..db import get_db
from ..models import AuditLog, FollowUpTask, HelpRequest, OutcomeFeedback, OutreachEvent, Participant
from ..services import care
from ..services.core import audit, now
from ..services.journey import (STAGES, active_appointment, journey, latest_finding, latest_pred, latest_rec,
                                latest_submitted, ser_appointment, ser_assessment, ser_finding, ser_participant_basic,
                                ser_prediction, ser_rec, ser_task)
from ..services.outreach import load_templates, suppress_all, tick
from ..services.risk_runner import create_pending, latest_for, latest_triage, run_in_background, ser_risk
from ..services.timeline import build_timeline

router = APIRouter(prefix="/api/gov", tags=["government"])
gov_only = require("government")


def get_p(db: Session, pid: int) -> Participant:
    p = db.get(Participant, pid)
    if not p:
        raise HTTPException(404, "Participant not found.")
    return p


@router.get("/worklist")
def worklist(actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    tick(db)
    db.commit()
    rows = []
    for p in db.scalars(select(Participant).order_by(Participant.id)):
        sub = latest_submitted(p)
        pred = latest_pred(sub)
        rec = latest_rec(sub)
        appt = active_appointment(p)
        f = latest_finding(p)
        j = journey(db, p)
        rows.append({
            "id": p.id,
            "code": p.code,
            "display_name": p.display_name,
            "governorate": p.governorate,
            "owner": p.owner,
            "contact_state": p.contact_state,
            "contact_channel": p.contact_channel,
            "opted_out": p.opted_out,
            "journey": j,
            "model": {"status": pred.status, "band": pred.band, "is_fixture": pred.is_fixture} if pred else None,
            "action": rec.action if rec else None,
            "clinician_review": rec.clinician_review if rec else False,
            "appointment": {"status": appt.status, "attendance": appt.attendance, "hospital_en": appt.hospital.name_en,
                            "hospital_ar": appt.hospital.name_ar, "confirmed_at": appt.confirmed_at.isoformat() if appt.confirmed_at else None}
            if appt else None,
            "finding_state": f.state if f else None,
            "next_review_date": f.next_review_date.isoformat() if f and f.next_review_date else None,
            "barriers": (sub.answers or {}).get("q_barriers") if sub else None,
        })
    order = {"high": 0, "medium": 1, "normal": 2}
    rows.sort(key=lambda r: (order[r["journey"]["priority"]], -r["journey"]["overdue_tasks"], -r["journey"]["open_tasks"], r["id"]))
    return rows


def pct(n: int, d: int) -> dict:
    return {"n": n, "d": d, "pct": round(100 * n / d, 1) if d else None}


@router.get("/metrics")
def metrics(actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    ps = list(db.scalars(select(Participant)))
    enrolled = len(ps)
    consented = sum(p.consent_given for p in ps)
    started = sum(1 for p in ps if p.assessments)
    submitted_ps = [p for p in ps if latest_submitted(p)]
    recs = {p.id: latest_rec(latest_submitted(p)) for p in submitted_ps}
    eligible = [p for p in submitted_ps if recs[p.id] and recs[p.id].booking_eligible]
    requested = [p for p in eligible if p.appointments]
    confirmed = [p for p in requested if any(a.confirmed_on for a in p.appointments)]
    attendance_recorded = [p for p in confirmed if any(a.attendance != "unknown" for a in p.appointments)]
    attended = [p for p in confirmed if any(a.attendance == "attended" for a in p.appointments)]
    missed_any = [p for p in ps if any(a.attendance == "missed" for a in p.appointments)]
    next_step = [p for p in attended if (f := latest_finding(p)) and f.state != "pending"]
    fu_open = [p for p in ps if (f := latest_finding(p)) and f.state in ("pending", "incomplete_suspicious", "biopsy_confirmed")]
    symptom_cases = [p for p in submitted_ps if recs[p.id] and recs[p.id].action == "clinical_assessment"]
    symptom_seen = [p for p in symptom_cases if any(a.attendance == "attended" for a in p.appointments)]
    preds = [latest_pred(latest_submitted(p)) for p in submitted_ps]
    model_ok = sum(1 for pr in preds if pr and pr.status == "ok")
    fixture = sum(1 for pr in preds if pr and pr.is_fixture)

    stage_counts = Counter(journey(db, p)["stage"] for p in ps)
    actions = Counter(r.action for r in recs.values() if r)
    bands = Counter((pr.band if pr and pr.status == "ok" else "pending") for pr in preds)
    barriers: Counter = Counter()
    for p in submitted_ps:
        for b in (latest_submitted(p).answers or {}).get("q_barriers", []) or []:
            if b not in ("none", "prefer_not"):
                barriers[b] += 1
    missed_reasons = Counter(a.missed_reason or "unknown" for p in ps for a in p.appointments if a.attendance == "missed")
    tasks = list(db.scalars(select(FollowUpTask)))
    open_tasks = [t for t in tasks if t.status == "open"]
    today = now(db).date()
    events = list(db.scalars(select(OutreachEvent)))

    return {
        "as_of": now(db).isoformat(),
        "demo_data": all(p.is_demo for p in ps) if ps else True,
        "funnel": [
            {"key": "enrolled", **pct(enrolled, enrolled)},
            {"key": "assessment_submitted", **pct(len(submitted_ps), enrolled)},
            {"key": "booking_eligible", **pct(len(eligible), len(submitted_ps))},
            {"key": "appointment_requested", **pct(len(requested), len(eligible))},
            {"key": "appointment_confirmed", **pct(len(confirmed), len(requested))},
            {"key": "attended_verified", **pct(len(attended), len(confirmed))},
            {"key": "next_step_recorded", **pct(len(next_step), len(attended))},
        ],
        "rates": {
            "consented": pct(consented, enrolled),
            "assessment_started": pct(started, enrolled),
            "attendance_among_recorded": pct(len(attended), len(attendance_recorded)),
            "missed_any": pct(len(missed_any), len(confirmed)),
            "symptom_cases_seen": pct(len(symptom_seen), len(symptom_cases)),
            "model_result_available": pct(model_ok, len(submitted_ps)),
            "fixture_results": pct(fixture, len(submitted_ps)),
            "opted_out": pct(sum(p.opted_out for p in ps), enrolled),
        },
        "follow_up_open": len(fu_open),
        "stage_counts": {s: stage_counts.get(s, 0) for s in STAGES},
        "actions": dict(actions),
        "bands": dict(bands),
        "barriers": dict(barriers),
        "missed_reasons": dict(missed_reasons),
        "tasks": {
            "open": len(open_tasks),
            "overdue": sum(1 for t in open_tasks if t.due_date and t.due_date < today),
            "by_kind": dict(Counter(t.kind for t in open_tasks)),
        },
        "outreach": dict(Counter(e.state for e in events)),
        "feedback_records": db.query(OutcomeFeedback).count(),
    }


@router.get("/participants/{pid}")
def detail(pid: int, actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    p = get_p(db, pid)
    sub = latest_submitted(p)
    audit(db, actor.name, "government", "record_viewed", "participant", p.id, p.id)
    db.commit()
    return {
        "participant": {**ser_participant_basic(p), "phone": p.phone},
        "journey": journey(db, p),
        "assessment": ser_assessment(sub, include_free_text=True),
        "prediction": ser_prediction(latest_pred(sub), staff=True),
        "recommendation": ser_rec(latest_rec(sub)),
        "appointments": [ser_appointment(a, "government") for a in reversed(p.appointments)],
        "finding": ser_finding(latest_finding(p), "government"),
        "risk_profile": ser_risk(latest_for(db, sub), staff=True),
        "note_triage": latest_triage(db, sub),
        "tasks": [ser_task(t) for t in reversed(p.tasks)],
        "help_requests": [{"id": h.id, "topic": h.topic, "message": h.message, "status": h.status,
                           "created_at": h.created_at.isoformat()}
                          for h in db.scalars(select(HelpRequest).where(HelpRequest.participant_id == p.id).order_by(HelpRequest.id.desc()))],
        "outreach": [ev_row(e) for e in db.scalars(select(OutreachEvent).where(OutreachEvent.participant_id == p.id).order_by(OutreachEvent.scheduled_at))],
        "timeline": build_timeline(p, "government"),
        "audit": [{"at": l.at.isoformat(), "actor": l.actor, "role": l.actor_role, "action": l.action, "detail": l.detail}
                  for l in db.scalars(select(AuditLog).where(AuditLog.participant_id == p.id).order_by(AuditLog.id.desc()).limit(60))],
    }


@router.post("/participants/{pid}/risk-profile")
def regenerate_risk(pid: int, background: BackgroundTasks, actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    """Re-run the long-term risk profile with the configured backend (for example after adding DR7_API_KEY)."""
    p = get_p(db, pid)
    sub = latest_submitted(p)
    if not sub:
        raise HTTPException(409, "No submitted assessment yet.")
    rec = create_pending(db, sub, actor.name)
    if not rec:
        raise HTTPException(409, "The risk profile feature is turned off (HEALTHIES_RISK_BACKEND=off).")
    audit(db, actor.name, "government", "risk_profile_requested", "risk_profile", rec.id, p.id)
    db.commit()
    if config.INLINE_JOBS:
        run_in_background(rec.id)
        db.expire_all()
        db.refresh(rec)
    else:
        background.add_task(run_in_background, rec.id)
    return ser_risk(rec, staff=True)


class OwnerIn(BaseModel):
    owner: Optional[str] = Field(None, max_length=80)


@router.post("/participants/{pid}/owner")
def set_owner(pid: int, body: OwnerIn, actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    p = get_p(db, pid)
    p.owner = (body.owner or "").strip() or None
    audit(db, actor.name, "government", "owner_assigned", "participant", p.id, p.id, owner=p.owner)
    db.commit()
    return {"ok": True}


class ContactStateIn(BaseModel):
    state: str = Field(..., pattern="^(reached|unreachable|reminded|not_contacted)$")
    note: Optional[str] = Field(None, max_length=300)


@router.post("/participants/{pid}/contact")
def contact_state(pid: int, body: ContactStateIn, actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    """Failed contact ('unreachable') is recorded separately from refusal/opt-out."""
    p = get_p(db, pid)
    if p.opted_out:
        raise HTTPException(409, "Participant opted out of contact.")
    p.contact_state = body.state
    audit(db, actor.name, "government", "contact_attempt_recorded", "participant", p.id, p.id, state=body.state, note=body.note)
    db.commit()
    return {"ok": True}


class OptOutIn(BaseModel):
    opted_out: bool
    note: Optional[str] = Field(None, max_length=300)


@router.post("/participants/{pid}/opt-out")
def opt_out(pid: int, body: OptOutIn, actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    p = get_p(db, pid)
    p.opted_out = body.opted_out
    p.opted_out_at = now(db) if body.opted_out else None
    p.contact_state = "opted_out" if body.opted_out else "not_contacted"
    if body.opted_out:
        suppress_all(db, p.id)
    audit(db, actor.name, "government", "opt_out_recorded" if body.opted_out else "opt_in_recorded", "participant", p.id, p.id, note=body.note)
    tick(db)
    db.commit()
    return {"ok": True}


class TaskIn(BaseModel):
    kind: str = Field(..., pattern="^(callback|barrier_support|clarification|staff_review|clinical_follow_up|reschedule)$")
    note: str = Field(..., min_length=2, max_length=500)
    due_date: Optional[date] = None
    owner: Optional[str] = None


@router.post("/participants/{pid}/tasks")
def add_task(pid: int, body: TaskIn, actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    p = get_p(db, pid)
    t = FollowUpTask(participant_id=p.id, kind=body.kind, status="open", note=body.note, owner=body.owner or actor.name,
                     due_date=body.due_date, created_at=now(db))
    p.tasks.append(t)
    db.flush()
    audit(db, actor.name, "government", "task_created", "task", t.id, p.id, kind=body.kind)
    db.commit()
    return ser_task(t)


class CloseTaskIn(BaseModel):
    resolution: str = Field(..., min_length=2, max_length=500)
    status: str = Field("done", pattern="^(done|cancelled)$")


@router.post("/tasks/{tid}/close")
def close_task(tid: int, body: CloseTaskIn, actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    t = db.get(FollowUpTask, tid)
    if not t:
        raise HTTPException(404, "Task not found.")
    if t.kind == "clinical_follow_up" and t.owner_role == "provider":
        raise HTTPException(409, "Clinical follow-up closes when the hospital records the outcome.")
    t.status = body.status
    t.resolution = body.resolution
    t.closed_at = now(db)
    t.closed_by = actor.name
    if t.kind == "help_request":
        for h in db.scalars(select(HelpRequest).where(HelpRequest.participant_id == t.participant_id, HelpRequest.status == "open")):
            h.status = "handled"
    audit(db, actor.name, "government", "task_closed", "task", t.id, t.participant_id, resolution=body.resolution)
    db.commit()
    return ser_task(t)


@router.post("/tasks/{tid}/claim")
def claim_task(tid: int, actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    t = db.get(FollowUpTask, tid)
    if not t:
        raise HTTPException(404, "Task not found.")
    t.owner = actor.name
    audit(db, actor.name, "government", "task_claimed", "task", t.id, t.participant_id)
    db.commit()
    return ser_task(t)


class BarrierIn(BaseModel):
    barrier: str = Field(..., pattern="^(transport|cost|worry|time|where|companion|other)$")
    note: Optional[str] = Field(None, max_length=300)
    new_hospital_id: Optional[int] = None
    preferred_date: Optional[date] = None
    preferred_time: Optional[str] = None


@router.post("/participants/{pid}/barrier")
def resolve_barrier(pid: int, body: BarrierIn, actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    """Record a barrier and (optionally) request a closer provider on her behalf."""
    p = get_p(db, pid)
    audit(db, actor.name, "government", "barrier_recorded", "participant", p.id, p.id, barrier=body.barrier, note=body.note)
    new_appt = None
    if body.new_hospital_id:
        missed = [a for a in p.appointments if a.attendance == "missed"]
        service = missed[-1].service if missed else None
        new_appt = care.request_appointment(db, p, body.new_hospital_id, body.preferred_date, body.preferred_time,
                                            f"Requested by programme staff ({body.barrier}). {body.note or ''}".strip(),
                                            actor.name, "government", replaces=missed[-1] if missed else None, service=service)
    for t in p.tasks:
        if t.status == "open" and t.kind in ("barrier_support", "reschedule"):
            t.status, t.closed_at, t.closed_by = "done", now(db), actor.name
            t.resolution = f"Barrier recorded ({body.barrier})" + (" and closer provider requested" if new_appt else "")
    db.commit()
    return {"ok": True, "appointment": ser_appointment(new_appt, "government") if new_appt else None}


def ev_row(e: OutreachEvent) -> dict:
    return {
        "id": e.id,
        "participant_id": e.participant_id,
        "template": e.template,
        "channel": e.channel,
        "simulated": e.simulated,
        "scheduled_at": e.scheduled_at.isoformat(),
        "state": e.state,
        "cancellation_reason": e.cancellation_reason,
        "related_task_id": e.related_task_id,
        "related_appointment_id": e.related_appointment_id,
        "body_preview": e.body_preview,
        "language": e.language,
        "processed_at": e.processed_at.isoformat() if e.processed_at else None,
    }


@router.get("/outreach")
def outreach(actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    tick(db)
    db.commit()
    events = db.scalars(select(OutreachEvent).order_by(OutreachEvent.scheduled_at.desc(), OutreachEvent.id.desc())).all()
    codes = {p.id: (p.code, p.display_name, p.opted_out) for p in db.scalars(select(Participant))}
    callbacks = db.scalars(select(FollowUpTask).where(FollowUpTask.kind == "callback").order_by(FollowUpTask.id.desc())).all()
    return {
        "now": now(db).isoformat(),
        "templates": load_templates(),
        "events": [{**ev_row(e), "participant_code": codes[e.participant_id][0], "participant_name": codes[e.participant_id][1],
                    "participant_opted_out": codes[e.participant_id][2]} for e in events],
        "callback_tasks": [{**ser_task(t), "participant_code": codes[t.participant_id][0]} for t in callbacks],
    }


@router.get("/tasks")
def all_tasks(actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    codes = {p.id: (p.code, p.display_name) for p in db.scalars(select(Participant))}
    rows = db.scalars(select(FollowUpTask).order_by(FollowUpTask.status.desc(), FollowUpTask.due_date, FollowUpTask.id)).all()
    return [{**ser_task(t), "participant_code": codes[t.participant_id][0], "participant_name": codes[t.participant_id][1]} for t in rows]


@router.get("/feedback")
def feedback(actor: Actor = Depends(gov_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(OutcomeFeedback).order_by(OutcomeFeedback.id.desc())).all()
    return [{"id": r.id, "participant_id": r.participant_id, "model_version": r.model_version, "score": r.score,
             "recommended_action": r.recommended_action, "outcome_state": r.outcome_state,
             "outcome_date": r.outcome_date.isoformat(), "verification_source": r.verification_source,
             "label_usable": r.label_usable, "note": r.follow_up_period_note} for r in rows]
