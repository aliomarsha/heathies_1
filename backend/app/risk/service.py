"""Long-term breast cancer risk profile (Dr7.ai gateway / MedGemma).

This is an EDUCATIONAL layer, separate from both Wassim's outcome model and the action policy:
  * it never changes the recommended action, priority, booking eligibility or tasks;
  * it describes long-term statistical risk factors only, never current disease;
  * it only ever sees a de-identified, allow-listed payload (see sanitize.py).

Backends (HEALTHIES_RISK_BACKEND):
  hybrid  (default) rules facts -> tier decided by Jev (rules floor) -> MedGemma rewrites the wording
  off | fixture | dr7 (remote Dr7.ai, LLM does everything) | local (Ollama / LM Studio, LLM does everything)
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import ValidationError

from .. import config
from .prompt import PROMPT_VERSION, build_messages
from .sanitize import PIIViolation, sanitized_payload
from .schema import MAX_ITEM_CHARS, MAX_ITEMS, RiskProfile
from .writer import RiskWording, as_facts, build_writer_messages, merge_wording
from ..decisions.service import decide_risk_tier

log = logging.getLogger("healthies.risk")

# Output guard: statements the profile must never make. Items matching are dropped.
_FORBIDDEN = [
    r"\byou (do not|don't) have (breast )?cancer\b", r"\bcancer[- ]free\b", r"\bno (need|reason) (for|to) (be )?screen",
    r"\b(you|she) (have|has|likely has) (breast )?cancer\b", r"\bdiagnos(is|ed|e) (of|with) cancer\b",
    r"\d+(\.\d+)?\s?%",
    "لا تحتاجين", "لا يوجد لديك سرطان", "ليس لديك سرطان",
]
_FORBIDDEN_RE = [re.compile(p, re.I) for p in _FORBIDDEN]


@dataclass
class RiskResult:
    status: str                      # ok | disabled | unavailable | error | blocked_pii
    backend: str
    model: Optional[str] = None
    profile: Optional[RiskProfile] = None
    mode: Optional[str] = None       # parse | json_fallback | fixture
    payload: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    is_fixture: bool = False
    dropped_items: list[str] = field(default_factory=list)
    decision: Optional[dict[str, Any]] = None   # how the tier was decided (hybrid)
    notes: list[str] = field(default_factory=list)


def _guard(profile: RiskProfile) -> tuple[RiskProfile, list[str]]:
    """Trim, cap and remove any item that crosses into diagnosis or false reassurance."""
    dropped: list[str] = []

    def clean(items: list[str]) -> list[str]:
        out = []
        for it in items:
            it = " ".join(str(it).split())[:MAX_ITEM_CHARS]
            if not it:
                continue
            if any(r.search(it) for r in _FORBIDDEN_RE):
                dropped.append(it)
                continue
            out.append(it)
        return out[:MAX_ITEMS]

    return RiskProfile(
        estimated_risk_tier=profile.estimated_risk_tier,
        non_modifiable_historical_factors=clean(profile.non_modifiable_historical_factors),
        modifiable_lifestyle_factors=clean(profile.modifiable_lifestyle_factors),
        clinical_screening_recommendations=clean(profile.clinical_screening_recommendations),
    ), dropped


# ------------------------------------------------------------------------- fixture -----
def _fixture(payload: dict[str, Any], language: str) -> RiskProfile:
    """Deterministic demo output so the UI works offline. Clearly labelled as demo in the UI."""
    f = payload["factors"]
    ar = language == "ar"
    hist, life, recs = [], [], []
    points = 0
    if f.get("personal_history") == "Yes":
        points += 3
        hist.append("إصابة سابقة بسرطان الثدي." if ar else "A previous breast cancer diagnosis.")
    if f.get("surveillance_plan") == "Yes":
        points += 3
        hist.append("خطة فحص خاصة أوصى بها طبيب (مثلًا بسبب نتيجة جينية)." if ar else "A doctor-advised special check plan (for example a gene result).")
    fam = sum(f.get(k) == "Yes" for k in ("family_maternal", "family_paternal"))
    if fam:
        points += fam
        hist.append(("وجود قريبة أو أكثر مصابة بسرطان الثدي أو المبيض." if ar else
                     "One or more relatives with breast or ovarian cancer."))
    band = f.get("age_band_years", "unknown")
    if band != "unknown" and int(band.split("-")[0]) >= 50:
        hist.append("يرتفع الخطر مع التقدّم في العمر." if ar else "Risk rises with age.")
    if f.get("menarche") == "Younger than 12":
        points += 0.5
        hist.append("بدء الدورة الشهرية قبل سن 12." if ar else "First period before age 12.")
    if f.get("first_birth") in ("I have not given birth", "30 or older"):
        points += 0.5
        hist.append("عدم الإنجاب أو أول ولادة بعد سن 30." if ar else "No births, or first birth at 30 or older.")
    if f.get("dense_breasts") == "Yes":
        points += 1
        hist.append("أنسجة ثدي كثيفة بحسب الطبيب." if ar else "Dense breast tissue reported by a doctor.")
    if f.get("hormone_therapy") == "Yes, I take it now":
        points += 0.5
        life.append("العلاج الهرموني الحالي لانقطاع الطمث؛ ناقشي مدّته مع طبيبكِ." if ar else "Current menopausal hormone therapy; review its duration with your doctor.")
    alc = f.get("alcohol", "")
    if alc in ("1 to 6 drinks a week", "7 or more drinks a week"):
        points += 0.5
        life.append("شرب الكحول؛ التقليل منه يخفّض الخطر." if ar else "Drinking alcohol; less alcohol lowers risk.")
    if f.get("activity") in ("Rarely or never", "1 or 2 days"):
        life.append("قلّة النشاط البدني؛ يساعد النشاط المنتظم على خفض الخطر." if ar else "Low physical activity; regular activity helps lower risk.")
    if f.get("smoking", "").startswith("Yes, I smoke"):
        life.append("التدخين (بما فيه النرجيلة)؛ الإقلاع مفيد للصحة عمومًا." if ar else "Smoking (including argileh); stopping benefits overall health.")
    if f.get("weight") == "Yes":
        life.append("زيادة الوزن بعد انقطاع الطمث." if ar else "Weight gain after menopause.")

    major = fam + 3 * (f.get("personal_history") == "Yes") + 3 * (f.get("surveillance_plan") == "Yes")
    minor = points - major
    tier = ("High" if major >= 2 else "Moderate" if major >= 1 or minor >= 1.5
            else "Average" if minor > 0 or hist else "Low")
    recs.append("اتّبعي برنامج الكشف بالماموغرام المناسب لعمركِ بحسب الإرشادات الوطنية." if ar else
                "Follow mammography screening for your age group as advised by national guidance.")
    if fam >= 1 or f.get("surveillance_plan") == "Yes":
        recs.append("ناقشي مع طبيبكِ ما إذا كانت الاستشارة الوراثية مناسبة لكِ." if ar else
                    "Ask a clinician whether genetic counselling is appropriate for you.")
    if life:
        recs.append("ناقشي مع طبيبكِ عادات نمط الحياة التي يمكن تحسينها." if ar else
                    "Discuss the lifestyle factors above with a clinician or nurse.")
    if f.get("symptoms") not in ("None of these", "unknown", None):
        recs.insert(0, "يجب أن يفحص طبيب التغيّر الذي ذكرتِه؛ يتابع فريق الرعاية ذلك." if ar else
                    "Have the change you reported checked by a clinician; your care team is arranging this.")
    return RiskProfile(estimated_risk_tier=tier, non_modifiable_historical_factors=hist,
                       modifiable_lifestyle_factors=life, clinical_screening_recommendations=recs)


# ------------------------------------------------------------------------- Dr7.ai ------
def _target(name: str) -> dict[str, Any]:
    """Connection settings for an OpenAI-compatible server: remote Dr7.ai or a local Ollama/LM Studio."""
    if name == "local":
        return {"base_url": config.LOCAL_LLM_BASE_URL, "api_key": config.LOCAL_LLM_API_KEY or "local",
                "model": config.LOCAL_LLM_MODEL, "timeout": config.LOCAL_LLM_TIMEOUT_SECONDS}
    return {"base_url": config.DR7_BASE_URL, "api_key": config.DR7_API_KEY,
            "model": config.DR7_MODEL, "timeout": config.DR7_TIMEOUT_SECONDS}


def _client(name: str = "dr7"):
    from openai import OpenAI  # imported lazily so the app runs without the SDK in fixture mode

    t = _target(name)
    return OpenAI(api_key=t["api_key"], base_url=t["base_url"], timeout=t["timeout"], max_retries=1)


def _parse_call(client, messages, model, schema=RiskProfile):
    """OpenAI SDK structured outputs: strict JSON schema derived from RiskProfile."""
    completions = client.chat.completions
    parse = getattr(completions, "parse", None) or client.beta.chat.completions.parse  # SDK 1.x fallback
    resp = parse(model=model, messages=messages, response_format=schema, temperature=0.1)
    msg = resp.choices[0].message
    if getattr(msg, "refusal", None):
        raise ValueError(f"Model refused: {msg.refusal}")
    if msg.parsed is None:
        raise ValueError("Model returned no parsed object.")
    return msg.parsed


def _json_fallback_call(client, messages, model, schema=RiskProfile):
    """For gateways that ignore or reject response_format: same schema, validated locally."""
    resp = client.chat.completions.create(model=model, messages=messages, temperature=0.1, max_tokens=900)
    text = (resp.choices[0].message.content or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Model reply contained no JSON object.")
    return schema.model_validate(json.loads(m.group(0)))


def _llm(payload: dict[str, Any], language: str, name: str) -> tuple[RiskProfile, str]:
    """Shared path for "dr7" (remote gateway) and "local" (Ollama / LM Studio on this computer)."""
    if name == "dr7" and not config.DR7_API_KEY:
        raise ConnectionError("DR7_API_KEY is not set.")
    model = _target(name)["model"]
    client = _client(name)
    try:
        return _parse_call(client, build_messages(payload, language), model), "parse"
    except Exception as exc:  # noqa: BLE001
        if config.DR7_STRUCTURED_MODE == "parse":
            raise
        cls = type(exc).__name__
        if cls in {"AuthenticationError", "PermissionDeniedError", "RateLimitError", "APIConnectionError",
                   "APITimeoutError", "NotFoundError"}:
            raise
        log.info("Structured parse unavailable (%s: %s); using validated JSON fallback.", cls, exc)
        return _json_fallback_call(client, build_messages(payload, language, json_fallback=True), model), "json_fallback"


# ------------------------------------------------------------------------- hybrid ------
_TRANSPORT_ERRORS = {"AuthenticationError", "PermissionDeniedError", "RateLimitError", "APIConnectionError",
                     "APITimeoutError", "NotFoundError"}


def _write(tier: str, facts: dict[str, list[str]], language: str, writer: str) -> tuple[RiskWording, str]:
    """MedGemma (local or Dr7) rephrases the facts. Raises on any failure; caller falls back to templates."""
    if writer == "dr7" and not config.DR7_API_KEY:
        raise ConnectionError("DR7_API_KEY is not set.")
    client, model = _client(writer), _target(writer)["model"]
    try:
        return _parse_call(client, build_writer_messages(tier, facts, language), model, RiskWording), "parse"
    except Exception as exc:  # noqa: BLE001
        if config.DR7_STRUCTURED_MODE == "parse" or type(exc).__name__ in _TRANSPORT_ERRORS:
            raise
        return _json_fallback_call(client, build_writer_messages(tier, facts, language, json_fallback=True),
                                   model, RiskWording), "json_fallback"


def _hybrid(payload: dict[str, Any], language: str, decision_backend: Optional[str],
            writer: Optional[str]) -> tuple[RiskProfile, str, str, dict[str, Any], list[str]]:
    notes: list[str] = []
    base = _fixture(payload, language)                     # 1. rules: facts + rule tier (the floor)
    dec = decide_risk_tier(payload, base.estimated_risk_tier, decision_backend)   # 2. Jev decides the tier
    if dec.note:
        notes.append(dec.note)
    facts = as_facts(base)
    writer = (writer or config.RISK_WRITER).lower()
    text_by, models = "templates", []
    models.append(config.JEV_MODEL if dec.source in ("jev", "rules_floor") else "rules")
    if writer in ("local", "dr7") and any(facts.values()):
        try:                                               # 3. MedGemma writes the wording
            wording, how = _write(dec.tier, facts, language, writer)
            facts, rejected = merge_wording(facts, wording)
            notes.extend(rejected)
            text_by = f"{writer}:{how}"
            models.append(_target(writer)["model"])
        except Exception as exc:  # noqa: BLE001 - wording falls back to reviewed templates
            cls = type(exc).__name__
            hint = " Is Ollama running?" if writer == "local" and cls in {"APIConnectionError", "APITimeoutError"} else ""
            notes.append(f"Writer unavailable ({cls}){hint}; template text used."[:300])
    else:
        models.append("templates")
    profile = RiskProfile(estimated_risk_tier=dec.tier, **facts)
    decision = {"source": dec.source, "tier": dec.tier, "rules_tier": dec.rules_tier, "jev_tier": dec.jev_tier,
                "confidence": dec.confidence, "text_by": text_by}
    return profile, f"tier:{dec.source}|text:{text_by}", " + ".join(models), decision, notes


# ------------------------------------------------------------------------- entry -------
def generate_risk_profile(answers: dict[str, Any], participant: Any, language: str = "en",
                          backend: Optional[str] = None, *, decision_backend: Optional[str] = None,
                          writer: Optional[str] = None, payload: Optional[dict[str, Any]] = None) -> RiskResult:
    """Never raises. Any failure is returned as a status the UI can show honestly."""
    name = (backend or config.RISK_BACKEND).lower()
    if name == "off":
        return RiskResult(status="disabled", backend=name)
    try:
        payload = payload or sanitized_payload(answers, participant)
    except PIIViolation as exc:
        log.warning("Risk profile blocked: %s", exc)
        return RiskResult(status="blocked_pii", backend=name, error=str(exc))
    try:
        decision, notes = None, []
        if name == "hybrid":
            profile, mode, model, decision, notes = _hybrid(payload, language, decision_backend, writer)
        elif name == "fixture":
            profile, mode, model = _fixture(payload, language), "fixture", "fixture-risk-0 (demo)"
        elif name in ("dr7", "local"):
            profile, mode = _llm(payload, language, name)
            model = _target(name)["model"]
        else:
            return RiskResult(status="error", backend=name, error=f"Unknown risk backend '{name}'.")
        profile, dropped = _guard(profile)
        return RiskResult(status="ok", backend=name, model=model, profile=profile, mode=mode, payload=payload,
                          is_fixture=name == "fixture", dropped_items=dropped, decision=decision, notes=notes)
    except (ConnectionError, TimeoutError) as exc:
        return RiskResult(status="unavailable", backend=name, payload=payload, error=str(exc))
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        return RiskResult(status="error", backend=name, payload=payload, error=f"Invalid model output: {exc}"[:500])
    except Exception as exc:  # noqa: BLE001 - network/SDK errors must not break the care journey
        cls = type(exc).__name__
        status = "unavailable" if cls in {"APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError"} else "error"
        if name == "local" and cls in {"APIConnectionError", "APITimeoutError"}:
            exc = ConnectionError(f"Local model server not reachable at {config.LOCAL_LLM_BASE_URL}. Is Ollama / LM Studio running?")
        if name == "local" and cls == "NotFoundError":
            exc = LookupError(f"Model '{config.LOCAL_LLM_MODEL}' not found locally. Run: ollama pull {config.LOCAL_LLM_MODEL}")
        log.exception("Risk profile call failed")
        return RiskResult(status=status, backend=name, payload=payload, error=f"{cls}: {exc}"[:500])


__all__ = ["generate_risk_profile", "RiskResult", "PROMPT_VERSION"]
