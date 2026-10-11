"""Decision layer: typed decisions from Jev, with deterministic rules as floor and fallback.

Safety contract (same as the rest of the platform):
  * The risk tier can never go BELOW the rule-based tier: Jev may raise it, never lower it.
  * Low-confidence or unreadable Jev answers fall back to the rules.
  * Free-text triage can only ADD a staff-review task, never remove or downgrade anything.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from .. import config
from . import jev

log = logging.getLogger("healthies.decisions")

TIERS = ["Low", "Average", "Moderate", "High"]
DECISION_VERSION = "decisions-v1"

TIER_QUESTION = {
    "risk_tier": {
        "type": "choice",
        "instructions": (
            "Classify this woman's LONG-TERM statistical risk of developing breast cancer compared with an average "
            "woman of the same age band, using established population risk factors (as in the Gail and Tyrer-Cuzick "
            "models). Do not judge whether she has cancer now. 'unknown' means missing information, not 'no'."
        ),
        "criteria": {
            "Low": "Fewer risk factors than typical for her age.",
            "Average": "Risk factors typical for her age.",
            "Moderate": "Some elevated factors, e.g. one close relative with breast or ovarian cancer, dense breasts, or several lifestyle/reproductive factors.",
            "High": "Strong factors, e.g. a known gene result or special surveillance plan, prior breast cancer, or several affected relatives.",
        },
    }
}

TRIAGE_QUESTIONS = {
    "mentions_breast_change": {
        "type": "noul",
        "instructions": "The note mentions a lump, pain, discharge, skin or nipple change, or any other breast change or symptom.",
    },
    "barrier": {
        "type": "choice",
        "instructions": "The main practical difficulty attending an appointment mentioned in the note.",
        "criteria": {
            "transport": "Transport, distance or travel",
            "cost": "Cost or money",
            "worry": "Fear, worry or anxiety",
            "time": "Work, family or caring duties, time",
            "where": "Not knowing where to go or how to book",
            "companion": "Needs someone to accompany her",
            "other": "Another difficulty",
            "none": "No difficulty mentioned",
        },
    },
}

# Rules fallback for triage (English + Arabic + Arabizi keywords). Deliberately broad.
# ASCII words match on word boundaries ("*" = prefix); Arabic matches as substrings.
_CHANGE_WORDS = [
    "lump*", "mass", "bump*", "swell*", "pain*", "hurt*", "discharg*", "blood*", "bleed*", "nipple*", "rash*",
    "dimpl*", "redness", "breast change*", "hard spot*", "kotle", "waja3", "wja3",
    "كتلة", "ورم", "انتفاخ", "ألم", "وجع", "إفراز", "افراز", "نزيف", "حلمة", "الحلمة", "احمرار", "تغيّر في الثدي", "تغير في الثدي",
]
_NEGATIONS = ["no lump", "no pain", "nothing", "لا يوجد", "لا شيء", "ما في"]
_BARRIER_WORDS = {
    "transport": ["transport", "far", "distance", "bus", "car", "taxi", "مواصلات", "بعيد", "سيارة", "طريق"],
    "cost": ["cost", "money", "pay", "expensive", "afford", "مال", "كلفة", "مصاري", "غالي", "دفع"],
    "worry": ["scared", "afraid", "fear", "worry", "anxious", "خائفة", "خايفة", "قلق", "خوف"],
    "time": ["work", "job", "kids", "children", "care for", "busy", "عمل", "شغل", "أولاد", "اولاد", "مشغولة"],
    "where": ["where", "how to book", "وين", "أين", "كيف احجز"],
    "companion": ["alone", "accompany", "with me", "وحدي", "لوحدي", "يرافقني", "معي"],
}


@dataclass
class TierDecision:
    tier: str
    source: str                 # "jev" | "rules" | "rules_floor"
    rules_tier: str
    jev_tier: Optional[str] = None
    confidence: Optional[float] = None
    note: Optional[str] = None


@dataclass
class TriageDecision:
    flag_breast_change: bool
    probability: Optional[float]
    barrier: Optional[str]
    source: str                 # "jev+rules" | "rules"
    note: Optional[str] = None


def state_from_payload(payload: dict[str, Any]) -> str:
    """Jev reads 'state' as text. English labels; Jev is strongest in English."""
    lines = [f"Sex: {payload.get('sex', 'female')}"]
    lines += [f"{k.replace('_', ' ')}: {v}" for k, v in payload["factors"].items()]
    return "Questionnaire answers (de-identified):\n" + "\n".join(lines)


def decide_risk_tier(payload: dict[str, Any], rules_tier: str, backend: Optional[str] = None) -> TierDecision:
    name = (backend or config.DECISION_BACKEND).lower()
    if name != "jev":
        return TierDecision(tier=rules_tier, source="rules", rules_tier=rules_tier)
    try:
        ans = jev.call(state_from_payload(payload), TIER_QUESTION)["risk_tier"]
    except jev.JevError as exc:
        log.info("Jev tier unavailable, using rules: %s", exc)
        return TierDecision(tier=rules_tier, source="rules", rules_tier=rules_tier, note=f"Jev fallback: {exc}"[:300])
    jt, conf = ans["value"], ans.get("confidence")
    if conf is not None and conf < config.JEV_MIN_CONFIDENCE:
        return TierDecision(tier=rules_tier, source="rules", rules_tier=rules_tier, jev_tier=jt, confidence=conf,
                            note=f"Jev confidence {conf:.2f} below {config.JEV_MIN_CONFIDENCE}; rules used.")
    if TIERS.index(jt) < TIERS.index(rules_tier):
        return TierDecision(tier=rules_tier, source="rules_floor", rules_tier=rules_tier, jev_tier=jt, confidence=conf,
                            note="Jev suggested a lower tier than the rules; the rule-based floor was kept.")
    return TierDecision(tier=jt, source="jev", rules_tier=rules_tier, jev_tier=jt, confidence=conf)


def _has(t: str, w: str) -> bool:
    if not w.isascii():
        return w in t
    if w.endswith("*"):
        return re.search(r"\b" + re.escape(w[:-1]), t) is not None
    return re.search(r"\b" + re.escape(w) + r"\b", t) is not None


def _rules_triage(text: str) -> tuple[bool, Optional[str]]:
    t = text.lower()
    hit = any(_has(t, w) for w in _CHANGE_WORDS)
    if hit and any(n in t for n in _NEGATIONS) and not any(_has(t, w) for w in ("lump*", "كتلة", "discharg*", "إفراز", "نزيف", "blood*")):
        hit = False
    barrier = next((b for b, ws in _BARRIER_WORDS.items() if any(_has(t, w) for w in ws)), None)
    return hit, barrier


def triage_note(scrubbed_text: str, backend: Optional[str] = None) -> TriageDecision:
    """Flags a free-text note for staff. The rules always run; Jev can only add a flag."""
    rules_flag, rules_barrier = _rules_triage(scrubbed_text)
    name = (backend or config.DECISION_BACKEND).lower()
    if name != "jev":
        return TriageDecision(rules_flag, None, rules_barrier, "rules")
    try:
        ans = jev.call("Note written by a participant to her care team:\n" + scrubbed_text, TRIAGE_QUESTIONS)
    except jev.JevError as exc:
        return TriageDecision(rules_flag, None, rules_barrier, "rules", note=f"Jev fallback: {exc}"[:300])
    p = ans["mentions_breast_change"]["probability"]
    barrier = ans["barrier"]["value"]
    return TriageDecision(rules_flag or p >= config.JEV_TRIAGE_THRESHOLD, p,
                          (None if barrier == "none" else barrier) or rules_barrier, "jev+rules")


def scrub_note(text: str, identifiers: list[str]) -> str:
    from ..risk.sanitize import scrub_text

    out = scrub_text(text)
    for ident in sorted({i for i in identifiers if i and len(i) >= 3}, key=len, reverse=True):
        out = re.sub(re.escape(ident), "[name]", out, flags=re.I)
    return out[:2000]
