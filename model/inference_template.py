"""TEMPLATE for Wassim - copy to model/inference.py and fill in.

The platform calls predict(request) once per submitted assessment when it is started with
HEALTHIES_MODEL_BACKEND=python. Contract: docs/MODEL_INTEGRATION.md (version 1.0).

Rules (from the team handbook):
  * Load the fitted pipeline ONCE at import time. Never re-fit anything on a user.
  * Unknown answers arrive as the string "unknown"; branching-skipped ones as "not_applicable".
    Handle them exactly as in training. Unknown is not "no".
  * If you cannot score (out-of-scope input), return score=None and band=None. The platform then
    shows "pending / staff review" - never a low-risk result.
  * Raise an exception for real failures. The platform catches it and degrades safely.
  * Do NOT read the free-text answer - it is not sent to the model.
"""
from __future__ import annotations

import math
from pathlib import Path

import joblib
import pandas as pd

HERE = Path(__file__).resolve().parent

MODEL_VERSION = "healthies-lr-0.1"            # bump on every retrain
TARGET_DEFINITION = "<exact dataset outcome and timing, e.g. 'cancer found in same diagnostic episode'>"
THRESHOLD_VERSION = "thr-0.1-provisional"      # bump whenever thresholds change
BAND_THRESHOLDS = {"intermediate": 0.10, "higher": 0.30}   # provisional, chosen on validation data
ESCALATION_THRESHOLD = 0.20                    # frozen before test evaluation

FEATURE_ORDER = [
    # must match the training columns exactly (names come from survey.json -> model_feature)
    "age_years",
    "family_history_maternal",
    "family_history_paternal",
    "menarche_age_group",
    "menopause_status",
    "hormone_therapy",
    "first_birth_age_group",
    "symptom_lump",
    "symptom_nipple_discharge",
    "symptom_skin_change",
    "symptom_nipple_change",
    "symptom_shape_change",
    "symptom_persistent_pain",
]

PIPELINE = joblib.load(HERE / "fitted_pipeline.joblib")


def _encode(v):
    return math.nan if v in ("unknown", "not_applicable") else v


def predict(request: dict) -> dict:
    feats = request["features"]
    missing = [c for c in FEATURE_ORDER if c not in feats]
    if missing:
        raise ValueError(f"schema mismatch, missing features: {missing}")

    X = pd.DataFrame([{c: _encode(feats[c]) for c in FEATURE_ORDER}], columns=FEATURE_ORDER)
    score = float(PIPELINE.predict_proba(X)[0][1])

    band = ("higher" if score >= BAND_THRESHOLDS["higher"]
            else "intermediate" if score >= BAND_THRESHOLDS["intermediate"] else "lower")
    review = score >= ESCALATION_THRESHOLD
    reasons = []
    if request.get("unknown_features"):
        reasons.append("SOME_INPUTS_UNKNOWN")
    if review:
        reasons.append("SCORE_ABOVE_ESCALATION_THRESHOLD")

    return {
        "model_version": MODEL_VERSION,
        "target_definition": TARGET_DEFINITION,
        "score": round(score, 4),
        "band": band,
        "review_flag": review,
        "reason_codes": reasons,
        "threshold_version": THRESHOLD_VERSION,
    }
