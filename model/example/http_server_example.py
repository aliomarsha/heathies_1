"""Optional: run the model as its own small service (HEALTHIES_MODEL_BACKEND=http).

    pip install fastapi uvicorn
    uvicorn http_server_example:app --port 9000      (from the folder containing inference.py)
"""
from fastapi import FastAPI, HTTPException

from inference import predict  # Wassim's predict(request) -> dict

app = FastAPI(title="Healthies model service")


@app.post("/predict")
def _predict(request: dict):
    try:
        return predict(request)
    except ValueError as exc:  # schema / input problems
        raise HTTPException(422, str(exc))
