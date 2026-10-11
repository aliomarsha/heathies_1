"""Live check of the Jev connection with a FICTIONAL, de-identified case.

    cd backend
    $env:JEV_API_KEY = "your-jev-key"          (PowerShell)
    python scripts/check_jev.py
Prints the raw reply so the response parser (app/decisions/jev.py: normalise) can be adjusted if
TypeSafe's final response format differs from the shapes it already accepts.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app import config  # noqa: E402
from app.decisions import jev  # noqa: E402
from app.decisions.service import TIER_QUESTION, TRIAGE_QUESTIONS, state_from_payload  # noqa: E402

payload = {"sex": "female", "factors": {"age_band_years": "45-49", "family_maternal": "Yes", "family_paternal": "unknown",
                                        "menarche": "Younger than 12", "activity": "1 or 2 days", "smoking": "Yes, I smoke now"}}
print("Endpoint:", config.JEV_URL, " model:", config.JEV_MODEL)
for name, state, qs in [("risk tier", state_from_payload(payload), TIER_QUESTION),
                        ("note triage", "Note written by a participant to her care team:\nI feel a small lump and I have no car.", TRIAGE_QUESTIONS)]:
    r = httpx.post(config.JEV_URL, json={"model": config.JEV_MODEL, "state": state, "questions": qs},
                   headers={"Authorization": f"Bearer {config.JEV_API_KEY}"}, timeout=15)
    print(f"\n[{name}] HTTP {r.status_code}\nraw: {r.text[:1500]}")
    if r.is_success:
        try:
            print("parsed:", json.dumps(jev.normalise(r.json(), qs), indent=1))
        except jev.JevFormatError as exc:
            print("PARSER NEEDS ADJUSTING:", exc)
