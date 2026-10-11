from __future__ import annotations

from typing import Any

from ..models import Participant
from .journey import iso


def build_timeline(p: Participant, role: str) -> list[dict[str, Any]]:
    """Chronological care events. Codes are translated by the frontend."""
    ev: list[dict[str, Any]] = []
    ev.append({"at": iso(p.consent_at or p.enrolled_at), "kind": "enrolled", "status": "done"})
    for a in p.assessments:
        if a.status == "submitted":
            ev.append({"at": iso(a.submitted_at), "kind": "assessment_submitted", "status": "done", "ref": a.public_id})
            for pr in a.predictions:
                ev.append({"at": iso(pr.created_at), "kind": "model_result" if pr.status == "ok" else "model_pending",
                           "status": "done" if pr.status == "ok" else "pending",
                           "band": pr.band if pr.status == "ok" else None})
            for r in a.recommendations:
                ev.append({"at": iso(r.created_at), "kind": "recommendation", "status": "done", "action": r.action})
        else:
            ev.append({"at": iso(a.updated_at), "kind": "assessment_draft", "status": "pending"})
    for ap in p.appointments:
        hosp = {"name_en": ap.hospital.name_en, "name_ar": ap.hospital.name_ar}
        ev.append({"at": iso(ap.created_at), "kind": "appointment_requested", "status": "done", "hospital": hosp,
                   "service": ap.service, "appointment_id": ap.id})
        if ap.confirmed_on:
            ev.append({"at": iso(ap.confirmed_on), "kind": "appointment_confirmed", "status": "done", "hospital": hosp,
                       "when": iso(ap.confirmed_at), "by": ap.confirmed_by if role != "participant" else None,
                       "appointment_id": ap.id})
        if ap.status in ("cancelled", "declined"):
            ev.append({"at": iso(ap.updated_at), "kind": f"appointment_{ap.status}", "status": "closed",
                       "reason": ap.cancel_reason, "appointment_id": ap.id})
        if ap.attendance != "unknown":
            ev.append({"at": iso(ap.attendance_on or ap.updated_at),
                       "kind": "attended" if ap.attendance == "attended" else "missed",
                       "status": "done" if ap.attendance == "attended" else "attention",
                       "verified": ap.attendance_verified, "source": ap.attendance_source,
                       "reason": ap.missed_reason if role != "participant" or ap.attendance == "missed" else None,
                       "appointment_id": ap.id})
        for f in ap.findings:
            state = f.state
            if role == "participant" and state == "biopsy_confirmed":
                state = "care_team_will_contact"
            ev.append({"at": iso(f.created_at), "kind": "finding", "status": "attention" if f.state in ("incomplete_suspicious", "biopsy_confirmed", "pending") else "done",
                       "state": state, "next_review_date": iso(f.next_review_date)})
    ev.sort(key=lambda e: e["at"] or "")
    return ev
