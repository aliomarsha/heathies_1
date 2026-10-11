"""Versioned request/response contract between the platform (Ali) and the model (Wassim).

See docs/MODEL_INTEGRATION.md for the human-readable version. If you change anything here,
bump CONTRACT_VERSION in config.py and tell the other side.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

ALLOWED_BANDS = ("lower", "intermediate", "higher")


@dataclass
class ModelRequest:
    contract_version: str
    assessment_id: str
    schema_version: str
    submitted_at: str  # ISO 8601
    features: dict[str, Any]  # model_feature -> value, unknown answers are the string "unknown"
    unknown_features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelResult:
    """Normalised outcome of a model call, whatever the backend.

    status: ok | unavailable | error | invalid_input
    Only status == "ok" carries a score/band. Anything else is shown as
    "assessment pending / staff review" - never as a low-risk result.
    """

    status: str
    backend: str
    is_fixture: bool = False
    model_version: Optional[str] = None
    target_definition: Optional[str] = None
    score: Optional[float] = None
    band: Optional[str] = None
    review_flag: bool = False
    reason_codes: list[str] = field(default_factory=list)
    threshold_version: Optional[str] = None
    raw_response: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None


REQUIRED_RESPONSE_FIELDS = (
    "model_version",
    "target_definition",
    "score",
    "band",
    "review_flag",
    "reason_codes",
    "threshold_version",
)


class ContractError(ValueError):
    pass


def validate_response(resp: Any) -> dict[str, Any]:
    """Raise ContractError if the model's response breaks the contract."""
    if not isinstance(resp, dict):
        raise ContractError("Model response must be a JSON object / dict.")
    missing = [k for k in REQUIRED_RESPONSE_FIELDS if k not in resp]
    if missing:
        raise ContractError(f"Model response missing fields: {', '.join(missing)}")
    score = resp["score"]
    if score is not None:
        try:
            score = float(score)
        except (TypeError, ValueError) as exc:
            raise ContractError("score must be a number between 0 and 1 or null") from exc
        if not 0.0 <= score <= 1.0:
            raise ContractError("score must be between 0 and 1")
    band = resp["band"]
    if band is not None and band not in ALLOWED_BANDS:
        raise ContractError(f"band must be one of {ALLOWED_BANDS} or null")
    if (score is None) != (band is None):
        raise ContractError("score and band must both be present or both be null")
    if not isinstance(resp["review_flag"], bool):
        raise ContractError("review_flag must be true/false")
    if not isinstance(resp["reason_codes"], list):
        raise ContractError("reason_codes must be a list of strings")
    out = dict(resp)
    out["score"] = score
    return out
