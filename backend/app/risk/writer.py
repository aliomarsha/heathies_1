"""MedGemma as WRITER only: rephrase rule-identified facts for a tier that is already decided.

The model cannot change the tier and cannot add risk factors that the rules did not find: any
section it leaves empty, overfills or makes unsafe falls back to the reviewed template text.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

WRITER_PROMPT_VERSION = "risk-writer-v1"


class RiskWording(BaseModel):
    model_config = ConfigDict(extra="forbid")
    non_modifiable_historical_factors: list[str]
    modifiable_lifestyle_factors: list[str]
    clinical_screening_recommendations: list[str]


WRITER_SYSTEM = """You write short, kind, plain-language explanations for a public-health breast screening programme.

You receive (1) a FIXED long-term risk tier that has already been decided and (2) the risk factors already identified from a woman's questionnaire.

Rules:
- Rewrite each listed factor as one clear sentence (under 25 words) in {language}. Keep the same meaning.
- Do NOT add risk factors that are not in the lists. Do NOT remove any. Keep the same number of items per list.
- Do NOT mention or change the tier. Do NOT give percentages.
- Never say or imply she does or does not have cancer now, or that she does not need screening.
- Recommendations are things to discuss with a clinician.
Return only the JSON object required by the schema."""

WRITER_JSON_SUFFIX = """

Respond with ONLY a JSON object, no markdown, with exactly these keys:
{"non_modifiable_historical_factors": [string], "modifiable_lifestyle_factors": [string], "clinical_screening_recommendations": [string]}"""


def build_writer_messages(tier: str, facts: dict[str, list[str]], language: str, *, json_fallback: bool = False):
    lang = "Arabic (Modern Standard, simple wording)" if language == "ar" else "English"
    system = WRITER_SYSTEM.replace("{language}", lang) + (WRITER_JSON_SUFFIX if json_fallback else "")
    user = json.dumps({"fixed_risk_tier": tier, "identified_factors": facts}, ensure_ascii=False, indent=2)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def merge_wording(facts: dict[str, list[str]], wording: RiskWording) -> tuple[dict[str, list[str]], list[str]]:
    """Accept the model's text per section only if it keeps the same item count; else use templates."""
    out, rejected = {}, []
    for key, fact_items in facts.items():
        written = [" ".join(str(x).split()) for x in getattr(wording, key) if str(x).strip()]
        if len(written) == len(fact_items):
            out[key] = written
        else:
            out[key] = fact_items
            if fact_items or written:
                rejected.append(f"{key}: model returned {len(written)} items for {len(fact_items)} facts; template text used")
    return out, rejected


def as_facts(profile: Any) -> dict[str, list[str]]:
    return {
        "non_modifiable_historical_factors": list(profile.non_modifiable_historical_factors),
        "modifiable_lifestyle_factors": list(profile.modifiable_lifestyle_factors),
        "clinical_screening_recommendations": list(profile.clinical_screening_recommendations),
    }
