"""Minimal client for TypeSafe's Jev ("System One") decision API.

Request format follows TypeSafe's published example (POST /v1/systemone):
    {"model": "jev-latest", "state": "<text>",
     "questions": {"<id>": {"type": "choice"|"noul"|"score", "instructions": "...",
                            "criteria": {"<option>": "<meaning>", ...}}}}

The exact RESPONSE layout was not published when this was written (Oct 2026), so `normalise()`
accepts the likely shapes and raises JevFormatError otherwise - callers then fall back to rules.
Run scripts/check_jev.py with a real key and adjust `normalise()` if needed.
"""
from __future__ import annotations

from typing import Any

from .. import config


class JevError(RuntimeError):
    pass


class JevUnavailable(JevError):
    pass


class JevFormatError(JevError):
    pass


def call(state: str, questions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Returns {question_id: {"value": ..., "probabilities": {...}, "confidence": float|None}}."""
    if not config.JEV_API_KEY:
        raise JevUnavailable("JEV_API_KEY is not set.")
    import httpx

    body = {"model": config.JEV_MODEL, "state": state, "questions": questions}
    try:
        r = httpx.post(config.JEV_URL, json=body, timeout=config.JEV_TIMEOUT_SECONDS,
                       headers={"Authorization": f"Bearer {config.JEV_API_KEY}"})
    except httpx.HTTPError as exc:
        raise JevUnavailable(f"{type(exc).__name__}: {exc}") from exc
    if r.status_code in (401, 403):
        raise JevUnavailable(f"Jev rejected the API key ({r.status_code}).")
    if r.status_code == 429 or r.status_code >= 500:
        raise JevUnavailable(f"Jev temporarily unavailable ({r.status_code}).")
    if r.status_code >= 400:
        raise JevFormatError(f"Jev rejected the request ({r.status_code}): {r.text[:300]}")
    return normalise(r.json(), questions)


_VALUE_KEYS = ("choice", "value", "answer", "result", "decision", "score")
_PROB_KEYS = ("probability", "p", "noul", "yes")
_DIST_KEYS = ("probabilities", "distribution", "probs", "scores")


def _answer(raw: Any, qtype: str) -> dict[str, Any]:
    if isinstance(raw, (int, float, str, bool)):
        raw = {"value": raw}
    if not isinstance(raw, dict):
        raise JevFormatError(f"Unexpected answer shape: {type(raw).__name__}")
    dist = next((raw[k] for k in _DIST_KEYS if isinstance(raw.get(k), dict)), {})
    conf = raw.get("confidence")
    if qtype == "noul":
        p = next((raw[k] for k in _PROB_KEYS if isinstance(raw.get(k), (int, float)) and not isinstance(raw.get(k), bool)), None)
        if p is None and isinstance(raw.get("value"), (int, float)) and not isinstance(raw.get("value"), bool):
            p = raw["value"]
        if p is None and isinstance(dist.get("yes"), (int, float)):
            p = dist["yes"]
        if p is None:
            raise JevFormatError("No probability in yes/no answer.")
        return {"value": float(p) >= 0.5, "probability": float(p), "confidence": conf}
    value = next((raw[k] for k in _VALUE_KEYS if k in raw and not isinstance(raw[k], dict)), None)
    if value is None and dist:
        value = max(dist, key=dist.get)
    if value is None:
        raise JevFormatError("No value in answer.")
    return {"value": value, "probabilities": dist, "confidence": conf}


def normalise(resp: Any, questions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    container = resp
    if isinstance(resp, dict):
        for key in ("answers", "results", "outputs", "decisions", "data"):
            if key in resp:
                container = resp[key]
                break
    if isinstance(container, list):  # [{"id"/"name"/"question": qid, ...}]
        container = {(i.get("id") or i.get("name") or i.get("question")): i for i in container if isinstance(i, dict)}
    if not isinstance(container, dict):
        raise JevFormatError("Response is not an object.")
    out = {}
    for qid, q in questions.items():
        if qid not in container:
            raise JevFormatError(f"Missing answer for '{qid}'.")
        out[qid] = _answer(container[qid], q["type"])
        if q["type"] == "choice" and out[qid]["value"] not in q["criteria"]:
            raise JevFormatError(f"Answer '{out[qid]['value']}' is not an allowed option for '{qid}'.")
    return out
