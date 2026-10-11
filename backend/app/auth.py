"""Very small token auth with three roles. Good enough for a prototype; swap for the
partner's identity provider before any real deployment."""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .config import SESSION_HOURS
from .db import get_db
from .models import SessionToken, User


@dataclass
class Actor:
    user: User

    @property
    def role(self) -> str:
        return self.user.role

    @property
    def name(self) -> str:
        return self.user.username


def issue_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(SessionToken(token=token, user_id=user.id, expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=SESSION_HOURS)))
    db.commit()
    return token


def current_actor(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Actor:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    token = authorization.split(" ", 1)[1].strip()
    row = db.get(SessionToken, token)
    if not row or row.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has ended. Sign in again.")
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not active.")
    return Actor(user)


def require(*roles: str):
    def dep(actor: Actor = Depends(current_actor)) -> Actor:
        if actor.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This area is not available for your role.")
        return actor

    return dep
