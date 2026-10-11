from __future__ import annotations

import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Actor, current_actor, issue_token
from ..db import get_db
from ..models import Hospital, Participant, SessionToken, User
from ..services.core import audit, hash_password, now, verify_password
from ..services.outreach import tick

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class ParticipantLoginIn(BaseModel):
    code: str
    pin: str


class ContactIn(BaseModel):
    channel: str = Field("sms", pattern="^(sms|call|none)$")
    time: str = Field("any", pattern="^(morning|afternoon|evening|any)$")
    safe_to_leave_message: bool = False
    discreet_messages: bool = True
    phone: Optional[str] = None


class EnrollIn(BaseModel):
    language: str = Field("ar", pattern="^(ar|en)$")
    display_name: Optional[str] = None
    consent: bool
    consent_version: str = "consent-v0.1-demo"
    contact: ContactIn = ContactIn()
    pin: str = Field(..., min_length=4, max_length=8, pattern=r"^\d+$")


def user_payload(db: Session, u: User) -> dict:
    d = {"id": u.id, "username": u.username, "role": u.role, "display_name": u.display_name}
    if u.hospital_id:
        h = db.get(Hospital, u.hospital_id)
        d["hospital"] = {"id": h.id, "name_en": h.name_en, "name_ar": h.name_ar} if h else None
    if u.participant_id:
        p = db.get(Participant, u.participant_id)
        d["participant_code"] = p.code if p else None
        d["language"] = p.language if p else None
    return d


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    if not u or u.role == "participant" or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Username or password is not correct.")
    return {"token": issue_token(db, u), "user": user_payload(db, u)}


@router.post("/participant-login")
def participant_login(body: ParticipantLoginIn, db: Session = Depends(get_db)):
    code = body.code.strip().upper()
    u = db.scalar(select(User).where(User.username == code.lower(), User.role == "participant"))
    if not u or not verify_password(body.pin.strip(), u.password_hash):
        raise HTTPException(401, "The code or PIN is not correct.")
    return {"token": issue_token(db, u), "user": user_payload(db, u)}


@router.post("/enroll")
def enroll(body: EnrollIn, db: Session = Depends(get_db)):
    if not body.consent:
        raise HTTPException(422, "Consent is needed to continue. You can still call for help without an account.")
    ts = now(db)
    for _ in range(20):
        code = f"HL-{secrets.randbelow(9000) + 1000}"
        if not db.scalar(select(Participant).where(Participant.code == code)):
            break
    p = Participant(
        code=code,
        display_name=(body.display_name or "").strip()[:80] or code,
        phone=(body.contact.phone or "").strip()[:30] or None,
        language=body.language,
        source="direct",
        enrolled_at=ts,
        consent_given=True,
        consent_version=body.consent_version,
        consent_at=ts,
        contact_channel=body.contact.channel,
        contact_time=body.contact.time,
        safe_to_leave_message=body.contact.safe_to_leave_message,
        discreet_messages=body.contact.discreet_messages,
        is_demo=True,
    )
    db.add(p)
    db.flush()
    u = User(username=code.lower(), password_hash=hash_password(body.pin), role="participant",
             display_name=p.display_name, participant_id=p.id)
    db.add(u)
    audit(db, code, "participant", "enrolled_with_consent", "participant", p.id, p.id,
          consent_version=body.consent_version, channel=body.contact.channel)
    tick(db)
    db.commit()
    return {"token": issue_token(db, u), "user": user_payload(db, u), "code": code}


@router.get("/me")
def me(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    return user_payload(db, actor.user)


@router.post("/logout")
def logout(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)):
    for t in db.scalars(select(SessionToken).where(SessionToken.user_id == actor.user.id)):
        db.delete(t)
    db.commit()
    return {"ok": True}
