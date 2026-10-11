"""Turn saved survey answers into the model feature dict defined by survey.json.

The mapping lives in survey.json (model_feature / encoding) so Wassim can change feature names
without touching Python. Unknown answers are passed as the literal string "unknown" - they are
never silently converted to "no".
"""
from __future__ import annotations

from typing import Any

from ..survey import is_visible, iter_questions, load_survey

UNKNOWN = "unknown"


def build_features(answers: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    survey = load_survey()
    features: dict[str, Any] = {}
    unknown: list[str] = []
    for q in iter_questions(survey):
        if q.get("group") != "model_input" or not q.get("model_feature"):
            continue
        name = q["model_feature"]
        visible = is_visible(q, answers)
        value = answers.get(q["id"]) if visible else None

        if q.get("encoding") == "multi_hot":
            opts = [o["value"] for o in q["options"] if not o.get("exclusive")]
            if not visible or value in (None, UNKNOWN) or (isinstance(value, list) and UNKNOWN in value) or not value:
                for o in opts:
                    features[f"{name}_{o}"] = UNKNOWN
                    unknown.append(f"{name}_{o}")
            else:
                chosen = set(value if isinstance(value, list) else [value])
                for o in opts:
                    features[f"{name}_{o}"] = 1 if o in chosen else 0
            continue

        if not visible:
            # Question not asked because of branching (e.g. hormone therapy before menopause).
            features[name] = "not_applicable"
            continue
        if value is None or value == "" or value == UNKNOWN:
            features[name] = UNKNOWN
            unknown.append(name)
        elif q["type"] == "number":
            try:
                features[name] = float(value)
            except (TypeError, ValueError):
                features[name] = UNKNOWN
                unknown.append(name)
        else:
            features[name] = value
    return features, unknown
