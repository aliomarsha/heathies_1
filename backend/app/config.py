"""Central configuration. Everything here can be overridden with environment variables
(or a `.env`-style export before starting the server)."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = Path(__file__).resolve().parent / "data"

# Running on Vercel? (Vercel sets VERCEL=1.) Serverless functions can only write to /tmp.
ON_VERCEL = bool(os.getenv("VERCEL"))


def _database_url() -> str:
    """HEALTHIES_DATABASE_URL wins. Otherwise use a Postgres URL that a Vercel storage integration
    (e.g. Neon) injects automatically. Otherwise SQLite: /tmp on Vercel, backend/healthies.db locally."""
    url = (os.getenv("HEALTHIES_DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL") or "").strip()
    if url:
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url
    if ON_VERCEL:
        return "sqlite:////tmp/healthies.db"
    return f"sqlite:///{BACKEND_DIR / 'healthies.db'}"


DATABASE_URL = _database_url()
# On Vercel, run post-submit jobs (risk profile, note check) inside the request: a serverless
# function may be frozen as soon as the response is sent, so background tasks are not reliable.
INLINE_JOBS = os.getenv("HEALTHIES_INLINE_JOBS", "1" if ON_VERCEL else "0") == "1"

# ---- Model integration -------------------------------------------------------
# "fixture"  : labelled demo responses (default until Wassim's model is ready)
# "python"   : import model/inference.py and call predict(request_dict)
# "sklearn"  : load model/fitted_pipeline.joblib + model/model_config.json
# "http"     : POST the request to HEALTHIES_MODEL_URL
MODEL_BACKEND = os.getenv("HEALTHIES_MODEL_BACKEND", "fixture").lower()
MODEL_DIR = Path(os.getenv("HEALTHIES_MODEL_DIR", PROJECT_DIR / "model"))
MODEL_URL = os.getenv("HEALTHIES_MODEL_URL", "http://127.0.0.1:9000/predict")
MODEL_TIMEOUT_SECONDS = float(os.getenv("HEALTHIES_MODEL_TIMEOUT", "5"))

CONTRACT_VERSION = "1.0"

# ---- Files the content team edits -------------------------------------------
SURVEY_FILE = Path(os.getenv("HEALTHIES_SURVEY_FILE", DATA_DIR / "survey.json"))
POLICY_FILE = Path(os.getenv("HEALTHIES_POLICY_FILE", DATA_DIR / "policy_config.json"))
HOSPITALS_FILE = Path(os.getenv("HEALTHIES_HOSPITALS_FILE", DATA_DIR / "hospitals.json"))
OUTREACH_FILE = Path(os.getenv("HEALTHIES_OUTREACH_FILE", DATA_DIR / "outreach_templates.json"))

FRONTEND_DIST = Path(os.getenv("HEALTHIES_FRONTEND_DIST", PROJECT_DIR / "frontend" / "dist"))

SESSION_HOURS = int(os.getenv("HEALTHIES_SESSION_HOURS", "12"))
DEMO_PASSWORD = os.getenv("HEALTHIES_DEMO_PASSWORD", "demo1234")

# Demo controls (reset / advance time / simulate outage). Set to 0 for anything beyond a demo.
DEMO_MODE = os.getenv("HEALTHIES_DEMO_MODE", "1") == "1"

# ---- Long-term risk profile (LLM via Dr7.ai gateway) -------------------------------
# "hybrid"  : DEFAULT, built for scale - tier decided by the decision layer (Jev or rules, rules as
#             a floor) and factor wording from clinician-reviewable templates; no text LLM per person
# "off"     : feature hidden
# "fixture" : deterministic, clearly-labelled demo profile (no network, default)
# "dr7"     : call the Dr7.ai OpenAI-compatible gateway with a de-identified payload
# "local"   : call a model running on this computer (Ollama or LM Studio) - nothing leaves the PC
RISK_BACKEND = os.getenv("HEALTHIES_RISK_BACKEND", "hybrid").lower()
DR7_API_KEY = os.getenv("DR7_API_KEY", "")
# Dr7.ai docs (Oct 2026) show POST https://dr7.ai/api/v1/medical/chat/completions; the OpenAI SDK
# appends "/chat/completions" to this base URL. Override if your dashboard shows another one.
DR7_BASE_URL = os.getenv("DR7_BASE_URL", "https://dr7.ai/api/v1/medical")
DR7_MODEL = os.getenv("DR7_MODEL", "medgemma-4b-it")
DR7_TIMEOUT_SECONDS = float(os.getenv("DR7_TIMEOUT", "45"))
# "auto": try .parse() with a strict JSON schema, fall back to JSON-in-text validated against the
# same schema if the gateway rejects response_format. "parse": structured outputs only.
DR7_STRUCTURED_MODE = os.getenv("DR7_STRUCTURED_MODE", "auto").lower()

# Local model (HEALTHIES_RISK_BACKEND=local). Defaults match Ollama + "ollama pull medgemma1.5".
# LM Studio: LOCAL_LLM_BASE_URL=http://localhost:1234/v1 and LOCAL_LLM_MODEL=<model id shown in LM Studio>
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "medgemma1.5")
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "")
LOCAL_LLM_TIMEOUT_SECONDS = float(os.getenv("LOCAL_LLM_TIMEOUT", "180"))

# ---- Decision layer: Jev (TypeSafe "System One") or rules --------------------------------
# Typed, non-text decisions (risk tier, free-text triage). "rules" = deterministic, no network.
# "jev" = TypeSafe Jev API, with rules as the safety floor and automatic fallback.
DECISION_BACKEND = os.getenv("HEALTHIES_DECISION_BACKEND", "rules").lower()
JEV_API_KEY = os.getenv("JEV_API_KEY", "")
JEV_URL = os.getenv("JEV_URL", "https://api.typesafe.ai/v1/systemone")
JEV_MODEL = os.getenv("JEV_MODEL", "jev-latest")
JEV_TIMEOUT_SECONDS = float(os.getenv("JEV_TIMEOUT", "5"))
JEV_MIN_CONFIDENCE = float(os.getenv("JEV_MIN_CONFIDENCE", "0.5"))
# A free-text note is flagged for staff when P(mentions a breast change) >= this. Low on purpose.
JEV_TRIAGE_THRESHOLD = float(os.getenv("JEV_TRIAGE_THRESHOLD", "0.3"))

# Who writes the wording in hybrid mode: "local" (MedGemma via Ollama, default), "dr7", or "templates".
# If the writer is unreachable, reviewed template text is used automatically.
# On Vercel there is no local Ollama, so the default there is the reviewed templates.
RISK_WRITER = os.getenv("HEALTHIES_RISK_WRITER", "templates" if ON_VERCEL else "local").lower()
# Reuse a stored result when an identical de-identified payload was already processed (huge saving at scale).
RISK_CACHE = os.getenv("HEALTHIES_RISK_CACHE", "1") == "1"
