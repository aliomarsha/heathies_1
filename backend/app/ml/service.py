"""Single entry point the rest of the platform uses: run_model(request) -> ModelResult.
Never raises. Any failure becomes status != "ok", which the UI shows as pending/staff review."""
from __future__ import annotations

import logging
from typing import Any, Optional

from .. import config
from .backends import BACKENDS
from .contract import ContractError, ModelResult, validate_response

log = logging.getLogger("healthies.model")


def active_backend(override: Optional[str] = None) -> str:
    return (override or config.MODEL_BACKEND).lower()


def run_model(request: dict[str, Any], *, force_failure: bool = False, backend: Optional[str] = None) -> ModelResult:
    name = active_backend(backend)
    if force_failure:
        return ModelResult(status="unavailable", backend=name, error_message="Demo control: model marked unavailable.")
    fn = BACKENDS.get(name)
    if fn is None:
        return ModelResult(status="error", backend=name, error_message=f"Unknown model backend '{name}'.")
    try:
        raw = fn(request)
    except (FileNotFoundError, ConnectionError, TimeoutError, ImportError) as exc:
        log.warning("model unavailable: %s", exc)
        return ModelResult(status="unavailable", backend=name, error_message=str(exc))
    except Exception as exc:  # noqa: BLE001 - any model bug must degrade safely
        cls = type(exc).__name__
        status = "unavailable" if cls in {"ConnectError", "ConnectTimeout", "ReadTimeout"} else "error"
        log.exception("model call failed")
        return ModelResult(status=status, backend=name, error_message=f"{cls}: {exc}")
    try:
        resp = validate_response(raw)
    except ContractError as exc:
        return ModelResult(status="invalid_input" if "input" in str(exc).lower() else "error", backend=name,
                           raw_response=raw if isinstance(raw, dict) else None, error_message=str(exc))
    if resp["score"] is None:
        # The model itself declined to score (e.g. out-of-scope input). Treat as pending review.
        return ModelResult(status="invalid_input", backend=name, raw_response=resp,
                           model_version=resp.get("model_version"), target_definition=resp.get("target_definition"),
                           reason_codes=list(resp.get("reason_codes", [])), review_flag=True,
                           threshold_version=resp.get("threshold_version"),
                           error_message="Model returned no score for this input.")
    return ModelResult(
        status="ok",
        backend=name,
        is_fixture=bool(resp.get("is_fixture", name == "fixture")),
        model_version=resp["model_version"],
        target_definition=resp["target_definition"],
        score=resp["score"],
        band=resp["band"],
        review_flag=resp["review_flag"],
        reason_codes=list(resp["reason_codes"]),
        threshold_version=resp["threshold_version"],
        raw_response=resp,
    )
