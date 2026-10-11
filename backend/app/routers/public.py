from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..ml.service import active_backend
from ..models import Hospital
from ..policy.action_policy import load_policy
from ..services.core import get_setting, now
from ..services.journey import ser_hospital
from ..survey import load_survey

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/survey")
def survey():
    return load_survey()


@router.get("/hospitals")
def hospitals(governorate: Optional[str] = None, service: Optional[str] = None, db: Session = Depends(get_db)):
    rows = db.scalars(select(Hospital).order_by(Hospital.id)).all()
    out = []
    for h in rows:
        if service and service not in h.services:
            continue
        d = ser_hospital(h)
        d["near"] = bool(governorate and h.governorate == governorate)
        out.append(d)
    out.sort(key=lambda d: (not d["near"], d["id"]))
    return out


@router.get("/meta")
def meta(db: Session = Depends(get_db)):
    return {
        "app": "Healthies",
        "contract_version": config.CONTRACT_VERSION,
        "model_backend": active_backend(),
        "model_is_fixture": active_backend() == "fixture",
        "demo_model_failure": get_setting(db, "demo_model_failure", "0") == "1",
        "policy_version": load_policy()["policy_version"],
        "survey_version": load_survey()["schema_version"],
        "sim_now": now(db).isoformat(),
        "sim_offset_days": float(get_setting(db, "sim_offset_days", "0")),
        "demo_mode": config.DEMO_MODE,
        "risk_backend": config.RISK_BACKEND,
        "risk_model": {"dr7": config.DR7_MODEL, "local": config.LOCAL_LLM_MODEL}.get(config.RISK_BACKEND),
        "decision_backend": config.DECISION_BACKEND,
        "risk_writer": config.RISK_WRITER,
    }


@router.get("/health")
def health():
    return {"ok": True}
