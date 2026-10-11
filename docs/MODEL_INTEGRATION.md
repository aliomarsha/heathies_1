# Model integration (Ali and Wassim)

**Contract version 1.0**

The platform already runs end to end with **fixture** responses. These are hand-written demo values and are labelled as such everywhere. When your model is ready, plugging it in takes one setting and no code changes in the app.

## The three layers stay separate

| Layer | Who | Where in the code | What it may do |
|---|---|---|---|
| Model prediction | Wassim | `model/` and `backend/app/ml/` | Return a score, a band, a review flag and reason codes for the dataset-defined outcome |
| Action policy | Jad (clinical criteria) and Ali | `backend/app/policy/action_policy.py` and `backend/app/data/policy_config.json` | Choose the next step from symptoms, history, unknowns and the screening plan |
| Care records | Ali | everything else | Track appointments, attendance, verified findings and follow-up |

The model can only **add** clinician review. It can never remove a symptom referral, cancel screening eligibility, or set a deadline. If the model fails, the participant sees *"being reviewed by the care team"*. The app opens a staff-review task and never shows an invented low-risk result. `backend/tests/` checks all of this.

## Pick one of four ways to plug in

Set `HEALTHIES_MODEL_BACKEND` before starting the backend.

| Value | What you provide | Best when |
|---|---|---|
| `fixture` (default) | nothing | the model is not ready yet |
| `python` | `model/inference.py` with `predict(request: dict) -> dict` | **recommended**: full control in Python |
| `sklearn` | `model/fitted_pipeline.joblib` and `model/model_config.json` | the model is a plain scikit-learn pipeline with `predict_proba` |
| `http` | a service that accepts `POST` JSON at `HEALTHIES_MODEL_URL` | the model runs elsewhere or in another environment |

### Option `python` (recommended)

1. Copy `model/inference_template.py` to `model/inference.py`.
2. Put your fitted pipeline next to it (for example `model/fitted_pipeline.joblib`).
3. Fill in `MODEL_VERSION`, `TARGET_DEFINITION`, `THRESHOLD_VERSION`, the thresholds and `FEATURE_ORDER`.
4. Check it: `python model/check_model.py --backend python`
5. Run the app with it:
   - Linux / macOS: `HEALTHIES_MODEL_BACKEND=python ./run.sh`
   - Windows: `set HEALTHIES_MODEL_BACKEND=python` then `run.bat`

### Option `sklearn`

Save the **whole fitted pipeline** (preprocessing and estimator) with `joblib.dump`, and write `model_config.json` like this:

```json
{
  "model_version": "healthies-lr-0.1",
  "target_definition": "cancer found within the same diagnostic episode",
  "threshold_version": "thr-0.1-provisional",
  "pipeline_file": "fitted_pipeline.joblib",
  "feature_order": ["age_years", "family_history_maternal", "..."],
  "positive_class_index": 1,
  "unknown_encoding": "nan",
  "band_thresholds": {"intermediate": 0.10, "higher": 0.30},
  "escalation_threshold": 0.20
}
```

`unknown_encoding: "nan"` turns `"unknown"` and `"not_applicable"` into `NaN`, so your imputer handles them. Use `"keep_string"` if your encoder learned `"unknown"` as its own category.

`model/example/` contains a working **plumbing-test** pipeline trained on random data, so you can see the format. Its scores mean nothing. Try it with:

```bash
python model/check_model.py --backend sklearn --model-dir model/example
```

### Option `http`

Run any service that takes the request JSON and returns the response JSON. `model/example/http_server_example.py` wraps `predict()` in about 10 lines. Configure it with `HEALTHIES_MODEL_URL` (default `http://127.0.0.1:9000/predict`) and `HEALTHIES_MODEL_TIMEOUT` (default 5 seconds). A timeout or a connection error is treated as "unavailable" (pending staff review).

## Request (platform to model)

See `model/sample_request.json`.

```json
{
  "contract_version": "1.0",
  "assessment_id": "AS-3F9A1C02B7",
  "schema_version": "survey-v0.1-provisional",
  "submitted_at": "2026-10-10T09:30:00",
  "features": {
    "age_years": 52.0,
    "symptom_lump": 0, "symptom_nipple_discharge": 0, "symptom_skin_change": 0,
    "symptom_nipple_change": 0, "symptom_shape_change": 0, "symptom_persistent_pain": 0,
    "family_history_maternal": "yes",
    "family_history_paternal": "unknown",
    "menarche_age_group": "12_13",
    "menopause_status": "post",
    "hormone_therapy": "never",
    "first_birth_age_group": "under_30"
  },
  "unknown_features": ["family_history_paternal"]
}
```

- Feature names and allowed values come from `backend/app/data/survey.json`: the `model_feature` and `options[].value` fields of every question with `"group": "model_input"`. You can rename features or add questions there without touching Python. Tell Ali and Jad when you do.
- `"unknown"` means the participant answered "I'm not sure" or "I prefer not to say". It is **never** converted to "no".
- `"not_applicable"` means the question was skipped by branching. For example, hormone therapy is not asked before menopause.
- Multi-select questions with `"encoding": "multi_hot"` become one 0/1 column per option (for example `symptom_lump`). If the participant answered "I'm not sure", every column is `"unknown"`.
- **The free-text answer is never sent to the model.** It is stored for staff review only, as the handbook requires.

## Response (model to platform)

See `model/sample_response.json`.

| Field | Type | Rule |
|---|---|---|
| `model_version` | string | Bump it on every retrain |
| `target_definition` | string | The exact dataset outcome and timing. Never "risk of cancer" in general |
| `score` | number from 0 to 1, or `null` | `null` means "cannot score this input" and becomes pending review |
| `band` | `"lower"`, `"intermediate"`, `"higher"` or `null` | Must be `null` exactly when `score` is `null` |
| `review_flag` | boolean | `true` when the score is at or above your escalation threshold |
| `reason_codes` | list of strings | For example `SOME_INPUTS_UNKNOWN`. Shown to staff only |
| `threshold_version` | string | Bump it whenever thresholds change |
| `is_fixture` | boolean, optional | Leave it out for a real model |

Anything that breaks these rules is rejected by `backend/app/ml/contract.py` and treated as an error. The participant then sees "pending review" and staff get a review task.

## Where the platform shows each field

- **Participant:** the band only, as a three-step scale labelled "prototype estimate", plus a sentence saying it is not a diagnosis. She never sees a percentage or a score.
- **Hospital and programme staff:** score, band, model version, target, threshold version, backend and reason codes, in the participant record.
- **Dashboard:** band distribution, the share of results that came from the model, and a notice whenever any result is a fixture.

## Feedback for future retraining (offline only)

When a hospital records a verified finding, an `outcome_feedback` row is saved. It holds the original answers, the prediction time, the model version, the score, the recommended action, the verification source, the outcome state and the outcome date. `label_usable` is `false` until someone reviews the label against your target definition. Negative imaging alone is not a cancer-negative label. Nothing retrains automatically.

Export the rows from SQLite with:

```bash
sqlite3 backend/healthies.db ".mode csv" ".headers on" "select * from outcome_feedback;"
```

## Checklist before the demo

- [ ] `python model/check_model.py --backend <yours>` passes
- [ ] `TARGET_DEFINITION` matches Mohammad's label definition word for word
- [ ] Thresholds were chosen on validation data and frozen before testing
- [ ] Demo controls ("Simulate model outage") still show "pending review"
- [ ] Any measured metric in the deck comes from your evaluation report, not from the app
