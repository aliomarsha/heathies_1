"""Builds a PLUMBING-TEST model from RANDOM SYNTHETIC rows.

Its scores mean nothing. It only proves the "sklearn" backend can load a fitted
ColumnTransformer + estimator pipeline, feed it survey features with unknowns,
and return a valid contract response. Never present its output as model performance.

    python model/example/make_plumbing_model.py
    HEALTHIES_MODEL_BACKEND=sklearn HEALTHIES_MODEL_DIR=model/example uvicorn app.main:app   (from backend/)
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

HERE = Path(__file__).resolve().parent
rng = np.random.default_rng(42)
N = 600

CATEGORICAL = {
    "family_history_maternal": ["yes", "no"],
    "family_history_paternal": ["yes", "no"],
    "menarche_age_group": ["under_12", "12_13", "14_plus"],
    "menopause_status": ["pre", "peri", "post"],
    "hormone_therapy": ["current", "past", "never", "not_applicable"],
    "first_birth_age_group": ["no_births", "under_30", "30_plus"],
}
SYMPTOMS = ["symptom_lump", "symptom_nipple_discharge", "symptom_skin_change",
            "symptom_nipple_change", "symptom_shape_change", "symptom_persistent_pain"]

df = pd.DataFrame({"age_years": rng.integers(30, 80, N).astype(float)})
for c, vals in CATEGORICAL.items():
    df[c] = rng.choice(vals, N)
for s in SYMPTOMS:
    df[s] = rng.choice([0.0, 1.0], N, p=[0.9, 0.1])
# sprinkle unknowns (NaN) the way the platform sends them
for c in df.columns:
    df.loc[rng.random(N) < 0.08, c] = np.nan
y = rng.random(N) < 0.1  # random labels -> meaningless model

numeric = ["age_years"] + SYMPTOMS
pre = ColumnTransformer([
    ("num", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)), ("sc", StandardScaler())]), numeric),
    ("cat", Pipeline([("imp", SimpleImputer(strategy="constant", fill_value="unknown")),
                      ("oh", OneHotEncoder(handle_unknown="ignore"))]), list(CATEGORICAL)),
])
pipe = Pipeline([("pre", pre), ("clf", LogisticRegression(class_weight="balanced", max_iter=500, random_state=0))])
pipe.fit(df, y)
joblib.dump(pipe, HERE / "fitted_pipeline.joblib")

config = {
    "model_version": "PLUMBING-TEST-0 (random synthetic data, not a model)",
    "target_definition": "NONE - synthetic random labels for integration testing only",
    "threshold_version": "plumbing-thr-0",
    "pipeline_file": "fitted_pipeline.joblib",
    "feature_order": list(df.columns),
    "positive_class_index": 1,
    "unknown_encoding": "nan",
    "band_thresholds": {"intermediate": 0.45, "higher": 0.55},
    "escalation_threshold": 0.55,
}
(HERE / "model_config.json").write_text(json.dumps(config, indent=2))
print("wrote", HERE / "fitted_pipeline.joblib", "and model_config.json")
