"""Relational records. Assessment, contact, appointment, verification and care states are
kept in separate tables/columns on purpose (handbook: "an appointment request is not
confirmed, an upload is not provider-verified, a missed appointment is not refusal, and
attendance does not close unresolved follow-up")."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))  # participant | provider | government
    display_name: Mapped[str] = mapped_column(String(120))
    hospital_id: Mapped[Optional[int]] = mapped_column(ForeignKey("hospitals.id"), nullable=True)
    participant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("participants.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SessionToken(Base):
    __tablename__ = "session_tokens"
    token: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Participant(Base):
    __tablename__ = "participants"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)  # fictional only
    language: Mapped[str] = mapped_column(String(5), default="ar")
    governorate: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="direct")  # direct | campaign_invite
    enrolled_at: Mapped[datetime] = mapped_column(DateTime)

    # consent & contact (contact state is separate from care state)
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    consent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    contact_channel: Mapped[str] = mapped_column(String(20), default="sms")  # sms | call | none
    contact_time: Mapped[str] = mapped_column(String(20), default="any")  # morning | afternoon | evening | any
    safe_to_leave_message: Mapped[bool] = mapped_column(Boolean, default=False)
    discreet_messages: Mapped[bool] = mapped_column(Boolean, default=True)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    opted_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    contact_state: Mapped[str] = mapped_column(String(30), default="not_contacted")
    # not_contacted | reminded | reached | unreachable | opted_out

    owner: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)  # programme staff owner
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)

    assessments: Mapped[list["Assessment"]] = relationship(back_populates="participant", order_by="Assessment.id")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="participant", order_by="Appointment.id")
    tasks: Mapped[list["FollowUpTask"]] = relationship(back_populates="participant", order_by="FollowUpTask.id")


class HelpRequest(Base):
    __tablename__ = "help_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"))
    topic: Mapped[str] = mapped_column(String(40))  # survey | booking | transport | cost | worry | other
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="open")


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"))
    schema_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | submitted
    answers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    free_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # stored outside model features
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    participant: Mapped[Participant] = relationship(back_populates="assessments")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="assessment", order_by="Prediction.id")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="assessment", order_by="Recommendation.id")


class Prediction(Base):
    """Model response (Wassim's layer). Kept separate from the action recommendation."""
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20))  # ok | unavailable | error | invalid_input
    backend: Mapped[str] = mapped_column(String(20))
    is_fixture: Mapped[bool] = mapped_column(Boolean, default=False)
    model_version: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    target_definition: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    band: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # lower | intermediate | higher
    review_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    threshold_version: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    raw_response: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    assessment: Mapped[Assessment] = relationship(back_populates="predictions")


class Recommendation(Base):
    """Action response (policy layer)."""
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"))
    prediction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("predictions.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(40))
    # routine_screening | clinical_assessment | plan_review | clarification | recently_screened
    service: Mapped[str] = mapped_column(String(40))  # what can be booked
    policy_version: Mapped[str] = mapped_column(String(40))
    booking_eligible: Mapped[bool] = mapped_column(Boolean)
    clinician_review: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[str] = mapped_column(String(10), default="normal")  # high | medium | normal
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    clinician_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    assessment: Mapped[Assessment] = relationship(back_populates="recommendations")


class Hospital(Base):
    __tablename__ = "hospitals"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    name_en: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str] = mapped_column(String(20))  # governmental | private | ngo
    governorate: Mapped[str] = mapped_column(String(40))
    district: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    services: Mapped[list[str]] = mapped_column(JSON, default=list)
    phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    cost_status: Mapped[str] = mapped_column(String(30), default="unknown")  # confirmed_free | confirmed_fee | unknown
    cost_note_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cost_note_ar: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    info_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    demo_slots: Mapped[list[str]] = mapped_column(JSON, default=list)  # simulated availability (weekday hours)
    is_demo_partner: Mapped[bool] = mapped_column(Boolean, default=False)


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"))
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.id"))
    recommendation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("recommendations.id"), nullable=True)
    service: Mapped[str] = mapped_column(String(40))
    # booking state
    status: Mapped[str] = mapped_column(String(30), default="requested")
    # requested | confirmed | reschedule_requested | cancelled | declined | closed
    preferred_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    preferred_time: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # appointment time
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    confirmed_on: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # attendance (verification state, separate from booking state)
    attendance: Mapped[str] = mapped_column(String(20), default="unknown")  # unknown | attended | missed
    attendance_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # provider | self_report
    attendance_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    attendance_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    attendance_on: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    missed_reason: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)  # barrier, not refusal
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    participant_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    replaces_id: Mapped[Optional[int]] = mapped_column(ForeignKey("appointments.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    participant: Mapped[Participant] = relationship(back_populates="appointments")
    hospital: Mapped[Hospital] = relationship()
    findings: Mapped[list["Finding"]] = relationship(back_populates="appointment", order_by="Finding.id")


class Finding(Base):
    """Verified finding + clinician-set next step. Only providers can write; participant sees a
    safe, plain-language version; programme staff see the state category, not clinical notes."""
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id", ondelete="CASCADE"))
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(30))
    # pending | negative_benign | incomplete_suspicious | biopsy_confirmed
    next_step: Mapped[str] = mapped_column(String(40))
    # await_result | routine_review | further_imaging | biopsy | specialist_referral | clinician_plan
    next_review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # clinician-set only
    clinician_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    clinical_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_source: Mapped[str] = mapped_column(String(30), default="provider_record")
    entered_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime)

    appointment: Mapped[Appointment] = relationship(back_populates="findings")


class FollowUpTask(Base):
    __tablename__ = "follow_up_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40))
    # callback | clinical_follow_up | barrier_support | clarification | staff_review | help_request | reschedule
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | done | cancelled
    owner: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    owner_role: Mapped[str] = mapped_column(String(20), default="government")
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    appointment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("appointments.id"), nullable=True)
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    participant: Mapped[Participant] = relationship(back_populates="tasks")


class OutreachEvent(Base):
    __tablename__ = "outreach_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"))
    template: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(20), default="sms")  # sms | staff_call
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)  # always True in this prototype
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    state: Mapped[str] = mapped_column(String(20), default="scheduled")
    # scheduled | simulated_sent | cancelled | suppressed
    cancellation_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    related_task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("follow_up_tasks.id"), nullable=True)
    related_appointment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("appointments.id"), nullable=True)
    body_preview: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(5), default="ar")
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class OutcomeFeedback(Base):
    """Future-learning record (offline supervised retraining only; nothing updates live)."""
    __tablename__ = "outcome_feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"))
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"))
    prediction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("predictions.id"), nullable=True)
    finding_id: Mapped[Optional[int]] = mapped_column(ForeignKey("findings.id"), nullable=True)
    assessment_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    prediction_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommended_action: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    verification_source: Mapped[str] = mapped_column(String(30))
    outcome_state: Mapped[str] = mapped_column(String(30))
    outcome_date: Mapped[datetime] = mapped_column(DateTime)
    follow_up_period_note: Mapped[str] = mapped_column(String(200))
    label_usable: Mapped[bool] = mapped_column(Boolean, default=False)  # set only after label review


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime)
    actor: Mapped[str] = mapped_column(String(80))
    actor_role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    participant_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class RiskProfileRecord(Base):
    """Educational long-term risk-factor profile (LLM). Kept apart from Prediction and
    Recommendation: it never drives the care pathway."""
    __tablename__ = "risk_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20))  # pending | ok | disabled | unavailable | error | blocked_pii
    backend: Mapped[str] = mapped_column(String(20))
    model: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(40))
    is_fixture: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str] = mapped_column(String(5), default="en")
    tier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    non_modifiable: Mapped[list[str]] = mapped_column(JSON, default=list)
    modifiable: Mapped[list[str]] = mapped_column(JSON, default=list)
    recommendations: Mapped[list[str]] = mapped_column(JSON, default=list)
    sent_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)  # de-identified only
    dropped_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    decision: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    notes: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    from_cache: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class NoteTriage(Base):
    """Jev / rules reading of the optional free-text note. Can only ADD a staff-review task."""
    __tablename__ = "note_triage"
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(20))
    flag_breast_change: Mapped[bool] = mapped_column(Boolean)
    probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    barrier: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
