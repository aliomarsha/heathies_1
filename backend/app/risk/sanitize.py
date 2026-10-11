"""PII sanitisation before anything leaves the server.

Three layers, in order:
  1. Allow-list   - only survey answers from approved question IDs are used. Name, phone, code,
                    assessment ID, governorate, free text and dates are never read.
  2. Generalise   - exact age becomes a 5-year band; answers become plain-English labels.
  3. Scrub + gate - every outgoing string is regex-scrubbed, then the final payload is checked
                    against the participant's known identifiers. If anything matches, dispatch is
                    blocked (PIIViolation) rather than "best-effort" sent.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

from ..survey import is_visible, question_map

# Questions whose answers may be shared with the external model (no free text, no location).
ALLOWED_QUESTIONS = [
    "q_age",
    "q_symptoms",              # included so the model is told explicitly NOT to assess current disease
    "q_personal_history",
    "q_family_maternal",
    "q_family_paternal",
    "q_surveillance_plan",
    "q_menarche",
    "q_menopause",
    "q_hormone_therapy",
    "q_first_birth",
    "q_breastfeeding",
    "q_dense_breasts",
    "q_last_mammogram",
    "q_alcohol",
    "q_activity",
    "q_smoking",
    "q_weight",
]

NEVER_SEND = {"q_governorate", "q_barriers", "free_text", "q_symptom_duration", "q_unresolved"}

_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"(?:\+?\d[\d\s().-]{6,}\d)"), "[number]"),         # phone numbers / long digit runs
    (re.compile(r"\bHL-\d{3,6}\b", re.I), "[id]"),                      # participant codes
    (re.compile(r"\bAS-[0-9A-F]{6,}\b", re.I), "[id]"),                 # assessment IDs
    (re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b"), "[date]"),     # dates
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "[date]"),
]


class PIIViolation(RuntimeError):
    """Raised when an identifier is still present after sanitisation. The request is not sent."""


def age_band(age: Any) -> str:
    if not isinstance(age, (int, float)):
        return "unknown"
    lo = int(age) // 5 * 5
    return f"{lo}-{lo + 4}"


def scrub_text(text: str) -> str:
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


def _label(q: dict[str, Any], value: Any) -> str:
    if value in (None, "", "unknown") or value == ["unknown"]:
        return "unknown"
    if q["type"] == "number":
        return str(value)
    vals = value if isinstance(value, list) else [value]
    labels = [next((o["label"]["en"] for o in q["options"] if o["value"] == v), str(v)) for v in vals]
    return "; ".join(labels)


def build_payload(answers: dict[str, Any]) -> dict[str, Any]:
    """Allow-listed, generalised, labelled representation of the survey answers."""
    qmap = question_map()
    factors: dict[str, str] = {}
    for qid in ALLOWED_QUESTIONS:
        if qid in NEVER_SEND:
            continue
        q = qmap.get(qid)
        if not q:
            continue
        key = qid.removeprefix("q_")
        if not is_visible(q, answers):
            factors[key] = "not applicable"
            continue
        if qid == "q_age":
            factors["age_band_years"] = age_band(answers.get(qid))
            continue
        factors[key] = scrub_text(_label(q, answers.get(qid)))
    return {"sex": "female", "factors": factors}


def identifiers_for(participant: Any) -> list[str]:
    """Values that must never appear in an outgoing payload."""
    out: list[str] = []
    for attr in ("code", "display_name", "phone"):
        v = getattr(participant, attr, None)
        if v:
            out.append(str(v))
            out.extend(p for p in re.split(r"[\s.,]+", str(v)) if len(p) >= 3)
    if getattr(participant, "phone", None):
        digits = re.sub(r"\D", "", participant.phone)
        if len(digits) >= 6:
            out.append(digits)
    return out


def assert_clean(payload: dict[str, Any], identifiers: Iterable[str]) -> None:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    blob_digits = re.sub(r"\D", "", blob)
    for ident in identifiers:
        s = ident.strip().lower()
        if not s:
            continue
        if s.isdigit():
            if s in blob_digits:
                raise PIIViolation("A phone-like identifier is present in the outgoing payload.")
        elif re.search(r"(?<![a-z])" + re.escape(s) + r"(?![a-z])", blob):
            raise PIIViolation("A participant identifier is present in the outgoing payload.")
    for pat, _ in _PATTERNS:
        if pat.search(blob):
            raise PIIViolation("An identifier pattern remained after scrubbing.")


def sanitized_payload(answers: dict[str, Any], participant: Any) -> dict[str, Any]:
    payload = build_payload(answers)
    assert_clean(payload, identifiers_for(participant))
    return payload
