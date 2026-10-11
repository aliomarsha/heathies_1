"""Shared helpers: simulated clock, settings, audit log, password hashing."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models import AuditLog, Setting


# ---- settings ------------------------------------------------------------------
def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    return row.value if row else default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


# ---- simulated clock -------------------------------------------------------------
# The demo can "advance time" so reminders and follow-ups become due during a pitch.
def sim_offset_days(db: Session) -> float:
    try:
        return float(get_setting(db, "sim_offset_days", "0"))
    except ValueError:
        return 0.0


def now(db: Session) -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0) + timedelta(days=sim_offset_days(db))


def advance_clock(db: Session, days: float) -> datetime:
    set_setting(db, "sim_offset_days", str(sim_offset_days(db) + days))
    db.flush()
    return now(db)


# ---- audit -------------------------------------------------------------------------
def audit(
    db: Session,
    actor: str,
    role: str,
    action: str,
    entity: str,
    entity_id: Optional[int] = None,
    participant_id: Optional[int] = None,
    **detail: Any,
) -> None:
    db.add(
        AuditLog(
            at=now(db),
            actor=actor,
            actor_role=role,
            action=action,
            entity=entity,
            entity_id=entity_id,
            participant_id=participant_id,
            detail={k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in detail.items()},
        )
    )


# ---- passwords -----------------------------------------------------------------------
def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt).split("$", 1)[1], digest)
