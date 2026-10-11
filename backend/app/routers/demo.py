"""Demo controls: reset, advance simulated time, simulate model outage. Prototype only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..seed import reset_demo
from ..services.core import advance_clock, get_setting, now, set_setting
from ..services.outreach import tick

from ..config import DEMO_MODE


def demo_enabled():
    if not DEMO_MODE:
        raise HTTPException(404, "Demo controls are disabled.")


router = APIRouter(prefix="/api/demo", tags=["demo"], dependencies=[Depends(demo_enabled)])


@router.post("/reset")
def reset():
    return reset_demo()


class AdvanceIn(BaseModel):
    days: float = Field(..., gt=0, le=60)


@router.post("/advance")
def advance(body: AdvanceIn, db: Session = Depends(get_db)):
    advance_clock(db, body.days)
    stats = tick(db)
    db.commit()
    return {"now": now(db).isoformat(), "offset_days": float(get_setting(db, "sim_offset_days", "0")), **stats}


class ModelFailIn(BaseModel):
    enabled: bool


@router.post("/model-failure")
def model_failure(body: ModelFailIn, db: Session = Depends(get_db)):
    set_setting(db, "demo_model_failure", "1" if body.enabled else "0")
    db.commit()
    return {"demo_model_failure": body.enabled}
