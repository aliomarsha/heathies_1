# Model drop-in folder (Wassim)

Put the trained model here. The full contract is in [`../docs/MODEL_INTEGRATION.md`](../docs/MODEL_INTEGRATION.md).

| File | Purpose |
|---|---|
| `inference_template.py` | Copy it to `inference.py` and fill in `predict(request) -> dict` |
| `check_model.py` | Runs the platform's own adapter on fictional cases and checks the contract, determinism, unknowns, schema mismatch and symptom override |
| `sample_request.json` / `sample_response.json` | One exchange, exactly as the platform sends and expects it |
| `example/` | A **plumbing-test** pipeline trained on random data (`make_plumbing_model.py`), plus `http_server_example.py`. Its scores are meaningless |

Quick start:

```bash
cp model/inference_template.py model/inference.py
# save your fitted pipeline as model/fitted_pipeline.joblib, edit inference.py
python model/check_model.py --backend python
HEALTHIES_MODEL_BACKEND=python ./run.sh
```
