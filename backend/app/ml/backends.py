"""Model backends. Pick one with HEALTHIES_MODEL_BACKEND = fixture | python | sklearn | http.

Every backend receives a ModelRequest dict and must return a dict that passes
contract.validate_response(). Errors are caught by ml/service.py and turned into a
"pending / staff review" result - never a made-up low-risk answer.
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
from typing import Any, Callable

from .. import config


# ---------------------------------------------------------------------------------
# 1. FIXTURE - clearly labelled demo responses (default until the real model exists)
# ---------------------------------------------------------------------------------
FIXTURE_THRESHOLDS = {"intermediate": 0.20, "higher": 0.40}


def fixture_predict(request: dict[str, Any]) -> dict[str, Any]:
    """Deterministic, hand-written points so demos are repeatable.
    This is NOT a model and its numbers mean nothing clinically."""
    f = request["features"]
    score = 0.05
    reasons: list[str] = ["FIXTURE_RESPONSE"]

    age = f.get("age_years")
    if isinstance(age, (int, float)):
        if age >= 50:
            score += 0.08
    for side in ("family_history_maternal", "family_history_paternal"):
        if f.get(side) == "yes":
            score += 0.12
            reasons.append("FAMILY_HISTORY_REPORTED")
    symptom_keys = [k for k in f if k.startswith("symptom_")]
    if any(f[k] == 1 for k in symptom_keys):
        score += 0.15
        reasons.append("SYMPTOM_REPORTED")
    if f.get("hormone_therapy") == "current":
        score += 0.04
    if f.get("menarche_age_group") == "under_12":
        score += 0.03
    if f.get("first_birth_age_group") in ("no_births", "30_plus"):
        score += 0.03
    if request.get("unknown_features"):
        reasons.append("SOME_INPUTS_UNKNOWN")

    score = round(min(score, 0.95), 3)
    band = "higher" if score >= FIXTURE_THRESHOLDS["higher"] else "intermediate" if score >= FIXTURE_THRESHOLDS["intermediate"] else "lower"
    return {
        "model_version": "fixture-0 (not a trained model)",
        "target_definition": "FIXTURE - no outcome target; demo data only",
        "score": score,
        "band": band,
        "review_flag": band == "higher",
        "reason_codes": list(dict.fromkeys(reasons)),
        "threshold_version": "fixture-thresholds-0",
        "is_fixture": True,
    }


# ---------------------------------------------------------------------------------
# 2. PYTHON - Wassim provides model/inference.py with predict(request: dict) -> dict
# ---------------------------------------------------------------------------------
_python_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def python_predict(request: dict[str, Any]) -> dict[str, Any]:
    global _python_fn
    if _python_fn is None:
        path = Path(config.MODEL_DIR) / "inference.py"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found")
        spec = importlib.util.spec_from_file_location("healthies_model_inference", path)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec and spec.loader
        spec.loader.exec_module(module)
        if not hasattr(module, "predict"):
            raise AttributeError("model/inference.py must define predict(request: dict) -> dict")
        _python_fn = module.predict
    return _python_fn(request)


# ---------------------------------------------------------------------------------
# 3. SKLEARN - drop fitted_pipeline.joblib + model_config.json into /model
# ---------------------------------------------------------------------------------
_sk_cache: dict[str, Any] = {}


def _load_sklearn() -> tuple[Any, dict[str, Any]]:
    if "pipe" not in _sk_cache:
        import joblib

        cfg_path = Path(config.MODEL_DIR) / "model_config.json"
        with open(cfg_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        pipe = joblib.load(Path(config.MODEL_DIR) / cfg.get("pipeline_file", "fitted_pipeline.joblib"))
        _sk_cache.update(pipe=pipe, cfg=cfg)
    return _sk_cache["pipe"], _sk_cache["cfg"]


def sklearn_predict(request: dict[str, Any]) -> dict[str, Any]:
    pipe, cfg = _load_sklearn()
    order: list[str] = cfg["feature_order"]
    feats = request["features"]
    missing = [c for c in order if c not in feats]
    if missing:
        raise ValueError(f"Request lacks model features: {missing}")
    unknown_as = cfg.get("unknown_encoding", "nan")  # "nan" or "keep_string"

    def enc(v: Any) -> Any:
        if v in ("unknown", "not_applicable") and unknown_as == "nan":
            return math.nan
        return v

    row = {c: enc(feats[c]) for c in order}
    try:
        import pandas as pd  # pipelines with ColumnTransformer expect named columns

        X = pd.DataFrame([row], columns=order)
    except ImportError:  # pragma: no cover
        X = [[row[c] for c in order]]
    proba = pipe.predict_proba(X)[0]
    score = float(proba[cfg.get("positive_class_index", 1)])
    th = cfg["band_thresholds"]
    band = "higher" if score >= th["higher"] else "intermediate" if score >= th["intermediate"] else "lower"
    review = score >= cfg.get("escalation_threshold", th["higher"])
    reasons = []
    if request.get("unknown_features"):
        reasons.append("SOME_INPUTS_UNKNOWN")
    if review:
        reasons.append("SCORE_ABOVE_ESCALATION_THRESHOLD")
    return {
        "model_version": cfg["model_version"],
        "target_definition": cfg["target_definition"],
        "score": round(score, 4),
        "band": band,
        "review_flag": bool(review),
        "reason_codes": reasons,
        "threshold_version": cfg["threshold_version"],
    }


# ---------------------------------------------------------------------------------
# 4. HTTP - Wassim runs a separate service; we POST the request JSON
# ---------------------------------------------------------------------------------
def http_predict(request: dict[str, Any]) -> dict[str, Any]:
    import httpx

    r = httpx.post(config.MODEL_URL, json=request, timeout=config.MODEL_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()


BACKENDS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "fixture": fixture_predict,
    "python": python_predict,
    "sklearn": sklearn_predict,
    "http": http_predict,
}


def reset_caches() -> None:
    global _python_fn
    _python_fn = None
    _sk_cache.clear()
