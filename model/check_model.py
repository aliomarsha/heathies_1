"""Integration check for Wassim's model. Runs the platform's own adapter on fictional cases.

    python model/check_model.py --backend python                    # model/inference.py
    python model/check_model.py --backend sklearn --model-dir model/example
    python model/check_model.py --backend http --url http://127.0.0.1:9000/predict
    python model/check_model.py --backend fixture

Exit code 0 = contract OK. These are STRUCTURAL checks with fictional inputs - not evaluation.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

ap = argparse.ArgumentParser()
ap.add_argument("--backend", default="python", choices=["fixture", "python", "sklearn", "http"])
ap.add_argument("--model-dir", default=str(ROOT / "model"))
ap.add_argument("--url", default=None)
args = ap.parse_args()
os.environ["HEALTHIES_MODEL_BACKEND"] = args.backend
os.environ["HEALTHIES_MODEL_DIR"] = str(Path(args.model_dir).resolve())
if args.url:
    os.environ["HEALTHIES_MODEL_URL"] = args.url

from app.ml.contract import ModelRequest  # noqa: E402
from app.ml.features import build_features  # noqa: E402
from app.ml.service import run_model  # noqa: E402
from app.policy.action_policy import decide  # noqa: E402

BASE = {
    "q_age": 52, "q_governorate": "beirut", "q_symptoms": ["none"], "q_personal_history": "no",
    "q_family_maternal": "no", "q_family_paternal": "no", "q_surveillance_plan": "no", "q_menarche": "12_13",
    "q_menopause": "post", "q_hormone_therapy": "never", "q_first_birth": "under_30",
    "q_last_mammogram": "over_2y", "q_unresolved": "no", "q_barriers": ["none"],
}
CASES = {
    "routine_due": ({}, "routine_screening"),
    "symptom_young": ({"q_age": 34, "q_symptoms": ["lump"], "q_symptom_duration": "not_checked", "q_menopause": "pre"}, "clinical_assessment"),
    "family_history": ({"q_family_maternal": "yes", "q_family_paternal": "yes"}, "routine_screening"),
    "many_unknowns": ({"q_age": "unknown", "q_symptoms": ["unknown"], "q_family_maternal": "unknown",
                       "q_menarche": "unknown", "q_menopause": "unknown"}, "clarification"),
    "premenopausal_skip_hrt": ({"q_age": 44, "q_menopause": "pre"}, "routine_screening"),
}

failures = 0


def req_for(answers: dict, aid: str) -> dict:
    feats, unknown = build_features(answers)
    return ModelRequest("1.0", aid, "check", "2026-01-01T00:00:00", feats, unknown).to_dict()


def check(name: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")


print(f"Backend: {args.backend}   model dir: {os.environ['HEALTHIES_MODEL_DIR']}\n")
for name, (over, expected_action) in CASES.items():
    answers = {**BASE, **over}
    if answers.get("q_menopause") not in ("peri", "post"):
        answers.pop("q_hormone_therapy", None)
    req = req_for(answers, f"CHECK-{name}")
    r1 = run_model(req)
    r2 = run_model(req)
    print(f"{name}: status={r1.status} band={r1.band} score={r1.score} version={r1.model_version}")
    if r1.status == "ok":
        check("contract fields present", bool(r1.model_version and r1.target_definition and r1.threshold_version))
        check("deterministic repeat", r1.score == r2.score and r1.band == r2.band, f"{r1.score} vs {r2.score}")
    elif name == "many_unknowns" and r1.status == "invalid_input":
        check("declined to score unknown-heavy input (allowed)", True)
    else:
        check("model returned a result", False, r1.error_message or "")
    d = decide(answers, r1)
    check(f"policy action = {expected_action}", d["action"] == expected_action, d["action"])
    if r1.status != "ok":
        check("failure routes to staff review", "MODEL_RESULT_PENDING" in d["reason_codes"])
    print()

# schema mismatch must degrade safely (no crash, no low-risk result)
bad = req_for(BASE, "CHECK-schema")
bad["features"].pop(next(iter(bad["features"])))
r = run_model(bad)
print(f"schema_mismatch: status={r.status} ({r.error_message})")
if args.backend == "fixture":
    print("  [SKIP] fixture ignores missing features")
else:
    check("missing feature is not scored", r.status != "ok")
    check("policy marks result pending", "MODEL_RESULT_PENDING" in decide(BASE, r)["reason_codes"])

print(f"\n{'ALL CHECKS PASSED' if not failures else f'{failures} CHECK(S) FAILED'}")
sys.exit(1 if failures else 0)
