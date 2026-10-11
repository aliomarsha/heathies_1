"""Runs the long-term risk profile and the free-text triage outside the submitting request, so a
slow or failing external model never delays or breaks the care journey."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db import SessionLocal
from ..decisions.service import DECISION_VERSION, scrub_note, triage_note
from ..models import Assessment, NoteTriage, RiskProfileRecord
from ..risk.prompt import PROMPT_VERSION
from ..risk.sanitize import PIIViolation, identifiers_for, sanitized_payload
from ..risk.service import generate_risk_profile
from ..risk.writer import WRITER_PROMPT_VERSION
from .core import audit, now
from .journey import iso
from .outreach import open_task

log = logging.getLogger("healthies.risk")


def create_pending(db: Session, a: Assessment, requested_by: str, backend: Optional[str] = None) -> Optional[RiskProfileRecord]:
    name = (backend or config.RISK_BACKEND).lower()
    if name == "off" or a.status != "submitted":
        return None
    rec = RiskProfileRecord(assessment_id=a.id, participant_id=a.participant_id, status="pending", backend=name,
                            prompt_version=PROMPT_VERSION, language=a.participant.language,
                            requested_by=requested_by, created_at=now(db))
    db.add(rec)
    db.flush()
    return rec


def _options(rec: RiskProfileRecord) -> dict[str, str]:
    # Demo reset must never hit the network: seeded profiles use rules + templates.
    if rec.requested_by == "seed":
        return {"decision_backend": "rules", "writer": "templates"}
    return {"decision_backend": config.DECISION_BACKEND, "writer": config.RISK_WRITER}


def _cache_key(payload: dict[str, Any], rec: RiskProfileRecord, opts: dict[str, str]) -> str:
    raw = json.dumps({"p": payload, "b": rec.backend, "l": rec.language, **opts,
                      "v": [PROMPT_VERSION, WRITER_PROMPT_VERSION, DECISION_VERSION,
                            config.DR7_MODEL, config.LOCAL_LLM_MODEL, config.JEV_MODEL]}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def complete(db: Session, rec: RiskProfileRecord) -> RiskProfileRecord:
    a = db.get(Assessment, rec.assessment_id)
    opts = _options(rec)
    payload = None
    try:
        payload = sanitized_payload(a.answers or {}, a.participant)
        rec.payload_hash = _cache_key(payload, rec, opts)
    except PIIViolation:
        pass  # generate_risk_profile reports blocked_pii

    cached = None
    if config.RISK_CACHE and rec.payload_hash and rec.backend != "fixture":
        cached = db.scalar(select(RiskProfileRecord).where(
            RiskProfileRecord.payload_hash == rec.payload_hash, RiskProfileRecord.status == "ok",
            RiskProfileRecord.id != rec.id).order_by(RiskProfileRecord.id.desc()).limit(1))
    if cached:
        for f in ("status", "model", "mode", "is_fixture", "sent_payload", "tier", "non_modifiable", "modifiable",
                  "recommendations", "dropped_items", "decision", "notes"):
            setattr(rec, f, getattr(cached, f))
        rec.from_cache, rec.error = True, None
    else:
        result = generate_risk_profile(a.answers or {}, a.participant, rec.language, backend=rec.backend,
                                       payload=payload, **opts)
        rec.status, rec.model, rec.mode = result.status, result.model, result.mode
        rec.is_fixture, rec.sent_payload, rec.error = result.is_fixture, result.payload, result.error
        rec.dropped_items, rec.decision, rec.notes = result.dropped_items, result.decision, result.notes
        if result.profile:
            rec.tier = result.profile.estimated_risk_tier
            rec.non_modifiable = result.profile.non_modifiable_historical_factors
            rec.modifiable = result.profile.modifiable_lifestyle_factors
            rec.recommendations = result.profile.clinical_screening_recommendations
    rec.completed_at = now(db)
    audit(db, "system", "system", "risk_profile_" + rec.status, "risk_profile", rec.id, rec.participant_id,
          backend=rec.backend, model=rec.model, mode=rec.mode, cached=rec.from_cache)
    return rec


def triage_assessment(db: Session, a: Assessment, decision_backend: Optional[str] = None) -> Optional[NoteTriage]:
    """Reads the optional note. A possible breast change ADDS a staff-review task; nothing is ever removed."""
    if not a.free_text:
        return None
    p = a.participant
    text = scrub_note(a.free_text, identifiers_for(p))
    d = triage_note(text, decision_backend)
    row = NoteTriage(assessment_id=a.id, participant_id=p.id, source=d.source, flag_breast_change=d.flag_breast_change,
                     probability=d.probability, barrier=d.barrier, note=d.note, created_at=now(db))
    db.add(row)
    if d.flag_breast_change:
        prob = f" (Jev probability {d.probability:.2f})" if d.probability is not None else ""
        open_task(db, p.id, "staff_review", f"The participant's note may describe a breast change{prob}. "
                  "Read the note and make sure a clinical assessment is offered.", dedupe_key=f"notechange:{a.id}", due_days=1)
    audit(db, "system", "system", "note_triaged", "assessment", a.id, p.id, source=d.source,
          flag=d.flag_breast_change, barrier=d.barrier)
    return row


def run_in_background(record_id: Optional[int], assessment_id: Optional[int] = None) -> None:
    """Entry point for FastAPI BackgroundTasks (own DB session). At national scale move this to a
    worker queue (Celery/RQ) - the function is already self-contained."""
    db = SessionLocal()
    try:
        if assessment_id:
            a = db.get(Assessment, assessment_id)
            if a:
                triage_assessment(db, a)
                db.commit()
        rec = db.get(RiskProfileRecord, record_id) if record_id else None
        if rec and rec.status == "pending":
            complete(db, rec)
            db.commit()
    except Exception:  # pragma: no cover - never let this crash the worker
        log.exception("background run failed")
        db.rollback()
    finally:
        db.close()


def latest_for(db: Session, assessment: Optional[Assessment]) -> Optional[RiskProfileRecord]:
    if not assessment:
        return None
    return db.scalar(select(RiskProfileRecord).where(RiskProfileRecord.assessment_id == assessment.id)
                     .order_by(RiskProfileRecord.id.desc()).limit(1))


def latest_triage(db: Session, assessment: Optional[Assessment]) -> Optional[dict[str, Any]]:
    if not assessment:
        return None
    t = db.scalar(select(NoteTriage).where(NoteTriage.assessment_id == assessment.id).order_by(NoteTriage.id.desc()).limit(1))
    if not t:
        return None
    return {"source": t.source, "flag_breast_change": t.flag_breast_change, "probability": t.probability,
            "barrier": t.barrier, "note": t.note, "created_at": iso(t.created_at)}


def ser_risk(rec: Optional[RiskProfileRecord], *, staff: bool) -> Optional[dict[str, Any]]:
    if not rec:
        return None
    d: dict[str, Any] = {
        "id": rec.id,
        "status": rec.status,
        "backend": rec.backend,
        "is_fixture": rec.is_fixture,
        "text_by": (rec.decision or {}).get("text_by"),
        "tier_by": (rec.decision or {}).get("source"),
        "language": rec.language,
        "created_at": iso(rec.created_at),
        "completed_at": iso(rec.completed_at),
    }
    if rec.status == "ok":
        d.update(estimated_risk_tier=rec.tier, non_modifiable_historical_factors=rec.non_modifiable,
                 modifiable_lifestyle_factors=rec.modifiable, clinical_screening_recommendations=rec.recommendations)
    if staff:
        d.update(model=rec.model, mode=rec.mode, prompt_version=rec.prompt_version, sent_payload=rec.sent_payload,
                 dropped_items=rec.dropped_items, error=rec.error, requested_by=rec.requested_by,
                 decision=rec.decision, notes=rec.notes or [], from_cache=rec.from_cache)
    return d
