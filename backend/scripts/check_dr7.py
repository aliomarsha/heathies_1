"""Live smoke test for the Dr7.ai risk-profile integration, using a FICTIONAL participant.

    cd backend
    set DR7_API_KEY=sk-dr7-...          (PowerShell: $env:DR7_API_KEY="sk-dr7-...")
    python scripts/check_dr7.py
Optional: DR7_BASE_URL, DR7_MODEL (default medgemma-4b-it), DR7_STRUCTURED_MODE=auto|parse
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.risk.service import generate_risk_profile  # noqa: E402

person = SimpleNamespace(code="HL-0000", display_name="Test Person", phone="+961 70 000 000")
answers = {
    "q_age": 47, "q_symptoms": ["none"], "q_personal_history": "no", "q_family_maternal": "yes",
    "q_family_paternal": "unknown", "q_surveillance_plan": "no", "q_menarche": "under_12", "q_menopause": "pre",
    "q_first_birth": "30_plus", "q_breastfeeding": "yes_less", "q_dense_breasts": "unknown",
    "q_last_mammogram": "never", "q_alcohol": "occasional", "q_activity": "low", "q_smoking": "current",
}
print(f"Endpoint: {config.DR7_BASE_URL}/chat/completions   model: {config.DR7_MODEL}   mode: {config.DR7_STRUCTURED_MODE}")
for lang in ("en", "ar"):
    r = generate_risk_profile(answers, person, lang, backend="dr7")
    print(f"\n[{lang}] status={r.status} mode={r.mode} error={r.error}")
    if lang == "en":
        print("sent payload:", json.dumps(r.payload, indent=1))
    if r.profile:
        print(json.dumps(r.profile.model_dump(), ensure_ascii=False, indent=1))
    if r.dropped_items:
        print("dropped by safety filter:", r.dropped_items)
sys.exit(0 if r.status == "ok" else 1)
