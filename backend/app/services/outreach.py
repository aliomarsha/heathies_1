"""Simulated outreach engine. NO real SMS gateway exists - every event has simulated=True and
'sending' only changes a database state. Message bodies never contain findings or scores."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import OUTREACH_FILE
from ..models import Appointment, FollowUpTask, OutreachEvent, Participant
from .core import now

ASSESSMENT_TEMPLATES = ("invitation", "assessment_reminder")


@lru_cache(maxsize=1)
def load_templates() -> dict[str, Any]:
    with open(OUTREACH_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def render(template: str, lang: str, **values: str) -> str:
    t = load_templates()["templates"][template]
    text = t.get(lang) or t["en"]
    for k, v in values.items():
        text = text.replace("{" + k + "}", v)
    return text


def _existing(db: Session, key: str) -> Optional[OutreachEvent]:
    return db.scalar(select(OutreachEvent).where(OutreachEvent.dedupe_key == key))


def _schedule(db: Session, p: Participant, template: str, at: datetime, key: str, *,
              channel: Optional[str] = None, appointment_id: Optional[int] = None,
              task_id: Optional[int] = None, **values: str) -> Optional[OutreachEvent]:
    """Create an event once (deduplicated by key). Opted-out participants get nothing new."""
    if p.opted_out or p.contact_channel == "none":
        return None
    if _existing(db, key):
        return None
    ev = OutreachEvent(
        participant_id=p.id,
        template=template,
        channel=channel or ("staff_call" if p.contact_channel == "call" else "sms"),
        simulated=True,
        scheduled_at=at,
        state="scheduled",
        related_appointment_id=appointment_id,
        related_task_id=task_id,
        body_preview=render(template, p.language, **values),
        language=p.language,
        dedupe_key=key,
        created_at=now(db),
    )
    db.add(ev)
    db.flush()
    return ev


def cancel_events(db: Session, participant_id: int, reason: str, *, templates: Optional[tuple[str, ...]] = None,
                  appointment_id: Optional[int] = None, keep_key: Optional[str] = None) -> int:
    q = select(OutreachEvent).where(OutreachEvent.participant_id == participant_id, OutreachEvent.state == "scheduled")
    n = 0
    for ev in db.scalars(q):
        if templates and ev.template not in templates:
            continue
        if appointment_id is not None and ev.related_appointment_id != appointment_id:
            continue
        if keep_key and ev.dedupe_key == keep_key:
            continue
        ev.state = "cancelled"
        ev.cancellation_reason = reason
        n += 1
    return n


def suppress_all(db: Session, participant_id: int) -> int:
    n = 0
    for ev in db.scalars(select(OutreachEvent).where(OutreachEvent.participant_id == participant_id,
                                                     OutreachEvent.state == "scheduled")):
        ev.state = "suppressed"
        ev.cancellation_reason = "Participant opted out of contact"
        n += 1
    return n


def _fmt_when(dt: Optional[datetime], lang: str) -> str:
    if not dt:
        return ""
    return dt.strftime("%d/%m/%Y %H:%M")


def open_task(db: Session, participant_id: int, kind: str, note: str, *, dedupe_key: Optional[str] = None,
              owner_role: str = "government", due_days: int = 2, appointment_id: Optional[int] = None,
              owner: Optional[str] = None) -> Optional[FollowUpTask]:
    if dedupe_key and db.scalar(select(FollowUpTask).where(FollowUpTask.dedupe_key == dedupe_key)):
        return None
    t = FollowUpTask(participant_id=participant_id, kind=kind, status="open", note=note, owner_role=owner_role,
                     owner=owner, due_date=(now(db) + timedelta(days=due_days)).date(), created_at=now(db),
                     dedupe_key=dedupe_key, appointment_id=appointment_id)
    owner_p = db.get(Participant, participant_id)
    if owner_p is not None:
        owner_p.tasks.append(t)
    else:
        db.add(t)
    db.flush()
    return t


def tick(db: Session) -> dict[str, int]:
    """Plan new events from current care states, cancel stale ones, and 'send' due ones."""
    seq = load_templates()["sequence"]
    current = now(db)
    stats = {"planned": 0, "sent": 0, "cancelled": 0, "tasks": 0}

    for p in db.scalars(select(Participant)):
        if p.opted_out:
            stats["cancelled"] += suppress_all(db, p.id)
            continue
        submitted = any(a.status == "submitted" for a in p.assessments)

        # --- assessment invitation / reminders / callback --------------------------------
        if not submitted:
            if p.source == "campaign_invite":
                if _schedule(db, p, "invitation", p.enrolled_at + timedelta(days=seq["invitation_delay_days"]), f"inv:{p.id}"):
                    stats["planned"] += 1
            for i, d in enumerate(seq["assessment_reminder_days"]):
                if _schedule(db, p, "assessment_reminder", p.enrolled_at + timedelta(days=d), f"arem:{p.id}:{i}"):
                    stats["planned"] += 1
            cb_at = p.enrolled_at + timedelta(days=seq["callback_after_days"])
            if current >= cb_at and p.contact_channel != "none":
                reminders = db.scalars(select(OutreachEvent).where(
                    OutreachEvent.participant_id == p.id, OutreachEvent.template == "assessment_reminder")).all()
                if reminders and all(r.state == "simulated_sent" for r in reminders):
                    t = open_task(db, p.id, "callback", "No response after the configured reminder sequence. "
                                  "Call to offer help completing the assessment.", dedupe_key=f"cbtask:{p.id}")
                    if t:
                        stats["tasks"] += 1
                        _schedule(db, p, "callback_task", cb_at, f"cb:{p.id}", channel="staff_call", task_id=t.id)
        else:
            stats["cancelled"] += cancel_events(db, p.id, "Assessment completed", templates=ASSESSMENT_TEMPLATES)
            for t in p.tasks:
                if t.kind == "callback" and t.status == "open" and t.dedupe_key == f"cbtask:{p.id}":
                    t.status = "cancelled"
                    t.resolution = "Assessment completed before callback"
                    t.closed_at = current
                    t.closed_by = "system"

        # --- appointment reminders ----------------------------------------------------------
        for a in p.appointments:
            hosp = a.hospital.name_ar if p.language == "ar" else a.hospital.name_en
            if a.status == "requested":
                if _schedule(db, p, "appointment_request_reminder",
                             a.created_at + timedelta(days=seq["appointment_request_reminder_days"]),
                             f"apreq:{a.id}", appointment_id=a.id):
                    stats["planned"] += 1
            else:
                stats["cancelled"] += cancel_events(db, p.id, f"Appointment {a.status}", templates=("appointment_request_reminder",), appointment_id=a.id)

            if a.status == "confirmed" and a.confirmed_at and a.attendance == "unknown":
                key = f"conf:{a.id}:{a.confirmed_at.isoformat()}"
                cancel_events(db, p.id, "Appointment time changed", templates=("confirmed_reminder",), appointment_id=a.id, keep_key=key)
                when = a.confirmed_at - timedelta(days=seq["confirmed_reminder_days_before"])
                if _schedule(db, p, "confirmed_reminder", max(when, a.confirmed_on or when), key, appointment_id=a.id,
                             hospital=hosp, when=_fmt_when(a.confirmed_at, p.language)):
                    stats["planned"] += 1
            elif a.status != "confirmed" or a.attendance != "unknown":
                stats["cancelled"] += cancel_events(db, p.id, "Appointment no longer upcoming", templates=("confirmed_reminder",), appointment_id=a.id)

    # --- "send" due events (simulation only) ------------------------------------------------
    for ev in db.scalars(select(OutreachEvent).where(OutreachEvent.state == "scheduled", OutreachEvent.scheduled_at <= current)):
        ev.state = "simulated_sent"
        ev.processed_at = current
        stats["sent"] += 1
        p = db.get(Participant, ev.participant_id)
        if p and p.contact_state in ("not_contacted",) and ev.channel == "sms":
            p.contact_state = "reminded"
    db.flush()
    return stats
