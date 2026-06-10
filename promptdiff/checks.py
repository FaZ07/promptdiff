"""Assertion engine: deterministic checks against model outputs."""

import difflib
import json
import re
from typing import Tuple

from .spec import Check


def run_check(check: Check, output: str) -> Tuple[bool, str]:
    """Evaluate one check against an output. Returns (passed, detail)."""
    t, v = check.type, check.value
    lower = output.lower()

    if t == "contains":
        ok = str(v).lower() in lower
        return ok, f"expected output to contain {v!r}"
    if t == "not_contains":
        ok = str(v).lower() not in lower
        return ok, f"expected output NOT to contain {v!r}"
    if t == "contains_any":
        ok = any(str(x).lower() in lower for x in v)
        return ok, f"expected output to contain one of {v!r}"
    if t == "equals":
        ok = output.strip() == str(v).strip()
        return ok, f"expected output to equal {v!r}"
    if t == "regex":
        ok = re.search(str(v), output) is not None
        return ok, f"expected output to match /{v}/"
    if t == "not_regex":
        ok = re.search(str(v), output) is None
        return ok, f"expected output NOT to match /{v}/"
    if t == "json_valid":
        try:
            json.loads(_extract_json(output))
            ok = True
        except (json.JSONDecodeError, ValueError):
            ok = False
        if not v:  # json_valid: false inverts
            ok = not ok
        return ok, "expected output to be valid JSON" if v else "expected output to be invalid JSON"
    if t == "json_keys":
        try:
            data = json.loads(_extract_json(output))
            missing = [k for k in v if k not in data]
            return not missing, f"missing JSON keys: {missing}"
        except (json.JSONDecodeError, ValueError, TypeError):
            return False, "output is not valid JSON, cannot check keys"
    if t == "max_chars":
        ok = len(output) <= int(v)
        return ok, f"output is {len(output)} chars, max allowed {v}"
    if t == "min_chars":
        ok = len(output) >= int(v)
        return ok, f"output is {len(output)} chars, min required {v}"
    if t == "similar_to":
        target = v["text"] if isinstance(v, dict) else str(v)
        threshold = float(v.get("threshold", 0.7)) if isinstance(v, dict) else 0.7
        ratio = difflib.SequenceMatcher(
            None, output.strip().lower(), target.strip().lower()
        ).ratio()
        ok = ratio >= threshold
        return ok, f"similarity {ratio:.2f}, threshold {threshold}"

    return False, f"unknown check type {t!r}"


def _extract_json(output: str) -> str:
    """Pull a JSON object/array out of a response that may have prose
    around it (models often wrap JSON in markdown fences or text)."""
    text = output.strip()
    if text.startswith("```"):
        # strip markdown fence
        lines = text.splitlines()
        body = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(body).strip()
    if text.startswith(("{", "[")):
        return text
    # find first { or [ to last } or ]
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        end = text.rfind(close_c)
        if start != -1 and end > start:
            return text[start:end + 1]
    raise ValueError("no JSON found in output")
