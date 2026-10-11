"""Derives the care-journey state for a participant and serialises records per role.

Role visibility:
  participant - own records; findings in safe plain-language form; a biopsy-confirmed result is
                never announced on the website (care team contacts her).
  provider    - full clinical detail for participants with an appointment at their hospital.
  government  - journey states, actions, tasks, finding *category* and next step; no clinical notes.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models import Appointment, Assessment, Finding, FollowUpTask, Participant, Prediction, Recommendation
from .core import now

STAGES = [
    "enrolled",
    "assessment_started",
    "assessment_submitted",
    "appointment_requested",
    "appointment_confirmed",
    "attended",
    "next_step_recorded",
]

OPEN_FINDING_STATES = {"pending", "incomplete_suspicious", "biopsy_confirmed"}


def iso(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def latest_submitted(p: Participant) -> Optional[Assessment]:
    subs = [a for a in p.assessments if a.status == "submitted"]
    return subs[-1] if subs else None


def current_draft(p: Participant) -> Optional[Assessment]:
    drafts = [a for a in p.assessments if a.status == "draft"]
    return drafts[-1] if drafts else None


def latest_rec(a: Optional[Assessment]) -> Optional[Recommendation]:
    return a.recommendations[-1] if a and a.recommendations else None


def latest_pred(a: Optional[Assessment]) -> Optional[Prediction]:
    return a.predictions[-1] if a and a.predictions else None


def active_appointment(p: Participant) -> Optional[Appointment]:
    live = [a for a in p.appointments if a.status not in ("cancelled", "declined")]
    return live[-1] if live else None


def latest_finding(p: Participant) -> Optional[Finding]:
    fs = [f for a in p.appointments for f in a.findings]
    return max(fs, key=lambda f: f.id) if fs else None


def journey(db: Session, p: Participant) -> dict[str, Any]:
    sub = latest_submitted(p)
    draft = current_draft(p)
    appt = active_appointment(p)
    finding = latest_finding(p)
    pred = latest_pred(sub)
    rec = latest_rec(sub)

    stage = "enrolled"
    if draft or sub:
        stage = "assessment_started"
    if sub:
        stage = "assessment_submitted"
    if appt:
        if appt.status in ("requested", "reschedule_requested"):
            stage = "appointment_requested"
        if appt.status == "confirmed":
            stage = "appointment_confirmed"
        if appt.attendance == "attended":
            stage = "attended"
    if finding and finding.state != "pending" and appt and appt.attendance == "attended":
        stage = "next_step_recorded"

    flags: list[str] = []
    if p.opted_out:
        flags.append("opted_out")
    if any(a.attendance == "missed" for a in p.appointments):
        last_missed = [a for a in p.appointments if a.attendance == "missed"][-1]
        if not appt or appt.id == last_missed.id or appt.attendance != "attended":
            flags.append("missed_appointment")
    if pred and pred.status != "ok":
        flags.append("result_pending")
    if finding and finding.state in OPEN_FINDING_STATES:
        flags.append("follow_up_open")
    if appt and appt.attendance == "attended" and (not finding):
        flags.append("finding_pending")
    if rec and rec.clinician_review:
        flags.append("clinician_review")
    if appt and appt.attendance_source == "self_report" and not appt.attendance_verified:
        flags.append("self_report_unverified")

    open_tasks = [t for t in p.tasks if t.status == "open"]
    current = now(db)
    overdue = [t for t in open_tasks if t.due_date and t.due_date < current.date()]

    priority = rec.priority if rec else "normal"
    if "follow_up_open" in flags or (rec and rec.action == "clinical_assessment" and stage not in ("attended", "next_step_recorded")):
        priority = "high"
    elif ("missed_appointment" in flags or "result_pending" in flags) and priority == "normal":
        priority = "medium"

    next_action = _next_action(stage, flags, rec, appt, finding)

    return {
        "stage": stage,
        "stage_index": STAGES.index(stage),
        "flags": flags,
        "priority": priority,
        "next_action": next_action,
        "open_tasks": len(open_tasks),
        "overdue_tasks": len(overdue),
    }


def _next_action(stage: str, flags: list[str], rec: Optional[Recommendation], appt: Optional[Appointment],
                 finding: Optional[Finding]) -> str:
    if "opted_out" in flags:
        return "no_contact_opted_out"
    if "follow_up_open" in flags:
        return "ensure_follow_up"
    if "finding_pending" in flags:
        return "await_verified_finding"
    if "missed_appointment" in flags and (not appt or appt.attendance == "missed"):
        return "resolve_barrier_rebook"
    if stage in ("enrolled", "assessment_started"):
        return "complete_assessment"
    if stage == "assessment_submitted":
        if rec and rec.action == "clarification":
            return "clarify_information"
        if rec and rec.action == "recently_screened":
            return "keep_planned_schedule"
        return "request_appointment"
    if stage == "appointment_requested":
        return "provider_confirmation"
    if stage == "appointment_confirmed":
        return "attend_appointment"
    if stage == "attended":
        return "await_verified_finding"
    if stage == "next_step_recorded":
        return "next_review_set" if finding and finding.next_review_date else "follow_clinician_plan"
    return "none"


# ---------------------------------------------------------------- serialisers ---------
def ser_prediction(pr: Optional[Prediction], *, staff: bool) -> Optional[dict[str, Any]]:
    if not pr:
        return None
    d = {
        "status": pr.status,
        "band": pr.band if pr.status == "ok" else None,
        "is_fixture": pr.is_fixture,
        "created_at": iso(pr.created_at),
    }
    if staff:
        d.update(
            backend=pr.backend,
            model_version=pr.model_version,
            target_definition=pr.target_definition,
            score=pr.score,
            review_flag=pr.review_flag,
            reason_codes=pr.reason_codes,
            threshold_version=pr.threshold_version,
            error_message=pr.error_message,
        )
    return d


def ser_rec(r: Optional[Recommendation]) -> Optional[dict[str, Any]]:
    if not r:
        return None
    return {
        "id": r.id,
        "action": r.action,
        "service": r.service,
        "policy_version": r.policy_version,
        "booking_eligible": r.booking_eligible,
        "clinician_review": r.clinician_review,
        "priority": r.priority,
        "reason_codes": r.reason_codes,
        "clinician_due_date": iso(r.clinician_due_date),
        "created_at": iso(r.created_at),
    }


def ser_hospital(h, lang: Optional[str] = None) -> dict[str, Any]:
    return {
        "id": h.id,
        "slug": h.slug,
        "name_en": h.name_en,
        "name_ar": h.name_ar,
        "sector": h.sector,
        "governorate": h.governorate,
        "district": h.district,
        "services": h.services,
        "phone": h.phone,
        "cost_status": h.cost_status,
        "cost_note_en": h.cost_note_en,
        "cost_note_ar": h.cost_note_ar,
        "info_verified": h.info_verified,
        "source_url": h.source_url,
        "demo_slots": h.demo_slots,
        "is_demo_partner": h.is_demo_partner,
    }


def ser_finding(f: Optional[Finding], role: str) -> Optional[dict[str, Any]]:
    if not f:
        return None
    if role == "participant":
        state = f.state
        next_step = f.next_step
        if f.state == "biopsy_confirmed":
            # The website never announces a diagnosis; the care team leads that conversation.
            state = "care_team_will_contact"
            next_step = "clinician_plan"
        return {
            "id": f.id,
            "state": state,
            "next_step": next_step,
            "next_review_date": iso(f.next_review_date),
            "verified": True,
            "recorded_at": iso(f.created_at),
        }
    d = {
        "id": f.id,
        "appointment_id": f.appointment_id,
        "state": f.state,
        "next_step": f.next_step,
        "next_review_date": iso(f.next_review_date),
        "verification_source": f.verification_source,
        "entered_by": f.entered_by,
        "clinician_name": f.clinician_name,
        "recorded_at": iso(f.created_at),
    }
    if role == "provider":
        d["clinical_note"] = f.clinical_note
    return d


def ser_appointment(a: Appointment, role: str) -> dict[str, Any]:
    d = {
        "id": a.id,
        "participant_id": a.participant_id,
        "hospital": ser_hospital(a.hospital),
        "service": a.service,
        "status": a.status,
        "preferred_date": iso(a.preferred_date),
        "preferred_time": a.preferred_time,
        "confirmed_at": iso(a.confirmed_at),
        "confirmed_by": a.confirmed_by,
        "confirmed_on": iso(a.confirmed_on),
        "attendance": a.attendance,
        "attendance_source": a.attendance_source,
        "attendance_verified": a.attendance_verified,
        "attendance_by": a.attendance_by,
        "attendance_on": iso(a.attendance_on),
        "missed_reason": a.missed_reason,
        "cancel_reason": a.cancel_reason,
        "participant_note": a.participant_note,
        "replaces_id": a.replaces_id,
        "created_at": iso(a.created_at),
        "updated_at": iso(a.updated_at),
        "findings": [ser_finding(f, role) for f in a.findings],
    }
    return d


def ser_task(t: FollowUpTask) -> dict[str, Any]:
    return {
        "id": t.id,
        "participant_id": t.participant_id,
        "kind": t.kind,
        "status": t.status,
        "owner": t.owner,
        "owner_role": t.owner_role,
        "due_date": iso(t.due_date),
        "note": t.note,
        "appointment_id": t.appointment_id,
        "created_at": iso(t.created_at),
        "closed_at": iso(t.closed_at),
        "closed_by": t.closed_by,
        "resolution": t.resolution,
    }


def ser_participant_basic(p: Participant) -> dict[str, Any]:
    return {
        "id": p.id,
        "code": p.code,
        "display_name": p.display_name,
        "language": p.language,
        "governorate": p.governorate,
        "source": p.source,
        "enrolled_at": iso(p.enrolled_at),
        "consent_given": p.consent_given,
        "consent_version": p.consent_version,
        "consent_at": iso(p.consent_at),
        "contact_channel": p.contact_channel,
        "contact_time": p.contact_time,
        "safe_to_leave_message": p.safe_to_leave_message,
        "discreet_messages": p.discreet_messages,
        "opted_out": p.opted_out,
        "opted_out_at": iso(p.opted_out_at),
        "contact_state": p.contact_state,
        "owner": p.owner,
        "is_demo": p.is_demo,
    }


def ser_assessment(a: Optional[Assessment], *, include_free_text: bool) -> Optional[dict[str, Any]]:
    if not a:
        return None
    d = {
        "id": a.id,
        "public_id": a.public_id,
        "schema_version": a.schema_version,
        "status": a.status,
        "answers": a.answers,
        "current_step": a.current_step,
        "created_at": iso(a.created_at),
        "updated_at": iso(a.updated_at),
        "submitted_at": iso(a.submitted_at),
    }
    if include_free_text:
        d["free_text"] = a.free_text
    return d
