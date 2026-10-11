import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="healthies-test-")
os.environ["HEALTHIES_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["HEALTHIES_MODEL_BACKEND"] = "fixture"
os.environ.setdefault("HEALTHIES_RISK_WRITER", "templates")
os.environ.setdefault("HEALTHIES_DECISION_BACKEND", "rules")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import reset_demo  # noqa: E402


@pytest.fixture()
def client():
    reset_demo()
    with TestClient(app) as c:
        yield c


def login(c, username, password="demo1234"):
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def enrol(c, lang="en", channel="sms"):
    r = c.post("/api/auth/enroll", json={"language": lang, "consent": True, "pin": "1111", "contact": {"channel": channel}})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}, r.json()["code"]


BASE_ANSWERS = {
    "q_age": 52, "q_governorate": "beirut", "q_symptoms": ["none"], "q_personal_history": "no",
    "q_family_maternal": "no", "q_family_paternal": "no", "q_surveillance_plan": "no", "q_menarche": "12_13",
    "q_menopause": "post", "q_hormone_therapy": "never", "q_first_birth": "under_30",
    "q_last_mammogram": "over_2y", "q_unresolved": "no", "q_barriers": ["none"],
}


def submit(c, h, **over):
    answers = {**BASE_ANSWERS, **over}
    answers = {k: v for k, v in answers.items() if v is not None}
    c.get("/api/me/assessment", headers=h)
    r = c.put("/api/me/assessment", headers=h, json={"answers": answers})
    assert r.status_code == 200, r.text
    r = c.post("/api/me/assessment/submit", headers=h)
    assert r.status_code == 200, r.text
    return r.json()
