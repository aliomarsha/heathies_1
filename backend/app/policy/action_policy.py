"""Recommended-action policy (separate from the model).

Implements the handbook rules, in priority order:
  1. A concerning symptom or unresolved investigation -> clinical assessment, even if the model
     score is low or a recent mammogram is recorded.
  2. Personal history / individual surveillance plan -> clinician plan review.
  3. Missing critical information -> clarification ("unknown does not mean negative").
  4. Asymptomatic and due under the screening plan -> routine screening request,
     regardless of a lower model score.
  5. A higher model band only ADDS clinician review; it never sets a deadline and never
     removes screening eligibility or a symptom referral.
  6. Model failure -> result pending + staff review; rules 1-4 still apply.

All thresholds live in data/policy_config.json and are PROVISIONAL until clinical review.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Optional

from ..config import POLICY_FILE
from ..ml.contract import ModelResult
from ..survey import question_map

UNKNOWN = "unknown"
BOOKABLE = {"routine_screening", "clinical_assessment", "plan_review"}
PRIORITY_ORDER = {"normal": 0, "medium": 1, "high": 2}


@lru_cache(maxsize=1)
def load_policy() -> dict[str, Any]:
    with open(POLICY_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def _concerning_symptoms(answers: dict[str, Any]) -> list[str]:
    q = question_map().get("q_symptoms")
    if not q:
        return []
    concerning = {o["value"] for o in q["options"] if o.get("concerning")}
    chosen = answers.get("q_symptoms") or []
    return [s for s in chosen if s in concerning]


def _raise(cur: str, new: str) -> str:
    return new if PRIORITY_ORDER[new] > PRIORITY_ORDER[cur] else cur


def decide(answers: dict[str, Any], model: Optional[ModelResult]) -> dict[str, Any]:
    cfg = load_policy()
    reasons: list[str] = []
    priority = "normal"
    action: Optional[str] = None

    symptoms = _concerning_symptoms(answers)
    symptom_status = answers.get("q_symptom_duration")
    if symptoms:
        action = "clinical_assessment"
        reasons.append("SYMPTOM_REPORTED")
        priority = "medium" if symptom_status == "checked_done" else "high"
        if symptom_status == "checked_waiting":
            reasons.append("UNRESOLVED_INVESTIGATION")
            priority = "high"

    if answers.get("q_unresolved") == "yes":
        action = "clinical_assessment"
        reasons.append("UNRESOLVED_INVESTIGATION")
        priority = "high"

    if action is None and (answers.get("q_personal_history") == "yes" or answers.get("q_surveillance_plan") == "yes"):
        action = "plan_review"
        if answers.get("q_personal_history") == "yes":
            reasons.append("PERSONAL_HISTORY")
        if answers.get("q_surveillance_plan") == "yes":
            reasons.append("INDIVIDUAL_SURVEILLANCE_PLAN")
        priority = _raise(priority, "medium")

    unknown_critical = [
        qid for qid in cfg["critical_questions"]
        if answers.get(qid) in (None, UNKNOWN) or answers.get(qid) == [UNKNOWN]
    ]
    if action is None and unknown_critical:
        action = "clarification"
        reasons.append("CRITICAL_INFO_UNKNOWN")
        priority = _raise(priority, "medium")

    if action is None:
        age = answers.get("q_age")
        min_age = cfg["screening_plan"]["campaign_min_age"]
        if isinstance(age, (int, float)) and age >= min_age:
            if answers.get("q_last_mammogram") in cfg["screening_plan"]["recent_mammogram_values"]:
                action = "recently_screened"
                reasons.append("RECENT_MAMMOGRAM_REPORTED")
            else:
                action = "routine_screening"
                reasons.append("DUE_UNDER_SCREENING_PLAN")
                if answers.get("q_last_mammogram") in (None, UNKNOWN):
                    reasons.append("LAST_MAMMOGRAM_UNKNOWN")
        else:
            action = "plan_review"
            reasons.append("BELOW_CAMPAIGN_AGE")

    # --- model overlay: can only add review, never remove care -------------------
    clinician_review = action in ("clinical_assessment", "plan_review")
    if model is None or model.status != "ok":
        reasons.append("MODEL_RESULT_PENDING")
        clinician_review = True if cfg.get("model_failure_creates_staff_review", True) else clinician_review
    else:
        if model.band == "higher" and cfg.get("higher_band_triggers_clinician_review", True):
            reasons.append("MODEL_HIGHER_BAND_REVIEW")
            clinician_review = True
            priority = _raise(priority, "medium")
        if model.review_flag and "MODEL_REVIEW_FLAG" not in reasons:
            reasons.append("MODEL_REVIEW_FLAG")
            clinician_review = True

    if answers.get("q_barriers") and not set(answers["q_barriers"]) & {"none", "prefer_not"}:
        reasons.append("PRACTICAL_BARRIER_REPORTED")

    return {
        "action": action,
        "service": cfg["services"][action],
        "policy_version": cfg["policy_version"],
        "booking_eligible": action in BOOKABLE,
        "clinician_review": clinician_review,
        "priority": priority,
        "reason_codes": list(dict.fromkeys(reasons)),
        "symptoms": symptoms,
        "unknown_critical": unknown_critical,
    }
