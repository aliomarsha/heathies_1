"""Survey configuration loading, branching and answer validation."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Iterator

from .config import SURVEY_FILE

UNKNOWN = "unknown"


@lru_cache(maxsize=1)
def load_survey() -> dict[str, Any]:
    with open(SURVEY_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def iter_questions(survey: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for section in survey["sections"]:
        yield from section["questions"]


def question_map() -> dict[str, dict[str, Any]]:
    return {q["id"]: q for q in iter_questions(load_survey())}


def is_visible(q: dict[str, Any], answers: dict[str, Any]) -> bool:
    cond = q.get("show_if")
    if not cond:
        return True
    val = answers.get(cond["question"])
    vals = val if isinstance(val, list) else [val]
    if "any_of" in cond:
        return any(v in cond["any_of"] for v in vals)
    if "none_of" in cond:
        return not any(v in cond["none_of"] for v in vals)
    return True


def clean_answers(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only known question IDs and allowed values. Used for drafts (partial is fine)."""
    qmap = question_map()
    out: dict[str, Any] = {}
    for qid, val in (raw or {}).items():
        q = qmap.get(qid)
        if not q or val is None:
            continue
        if q["type"] == "number":
            if val == UNKNOWN:
                out[qid] = UNKNOWN
                continue
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            if q.get("min") is not None and num < q["min"]:
                continue
            if q.get("max") is not None and num > q["max"]:
                continue
            out[qid] = int(num) if num.is_integer() else num
        elif q["type"] == "single":
            allowed = {o["value"] for o in q["options"]}
            if val in allowed:
                out[qid] = val
        elif q["type"] == "multi":
            allowed = {o["value"] for o in q["options"]}
            exclusive = {o["value"] for o in q["options"] if o.get("exclusive")}
            vals = [v for v in (val if isinstance(val, list) else [val]) if v in allowed]
            vals = list(dict.fromkeys(vals))
            ex = [v for v in vals if v in exclusive]
            if ex:
                vals = [ex[-1]]
            if vals:
                out[qid] = vals
    return out


def missing_required(answers: dict[str, Any]) -> list[str]:
    missing = []
    for q in iter_questions(load_survey()):
        if q.get("required") and is_visible(q, answers) and q["id"] not in answers:
            missing.append(q["id"])
    return missing


def strip_hidden(answers: dict[str, Any]) -> dict[str, Any]:
    """Drop answers to questions that are no longer visible after a branch changed."""
    qmap = question_map()
    return {k: v for k, v in answers.items() if k in qmap and is_visible(qmap[k], answers)}
