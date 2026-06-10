"""Suite loading: parse promptdiff.yaml into typed objects."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass
class Check:
    """A single assertion against a model output."""
    type: str
    value: Any


@dataclass
class Case:
    """One test case: an input plus the checks its output must satisfy."""
    name: str
    input: str
    checks: List[Check] = field(default_factory=list)


@dataclass
class Suite:
    provider: str
    model: str
    command: str
    max_tokens: int
    prompts: Dict[str, str]   # version name -> prompt text
    cases: List[Case]
    base_dir: Path


VALID_CHECKS = {
    "contains", "not_contains", "contains_any", "equals",
    "regex", "not_regex", "json_valid", "json_keys",
    "max_chars", "min_chars", "similar_to",
}


def load(path: str) -> Suite:
    """Load and validate a suite YAML file.

    Prompt values may be inline text or a path (relative to the suite
    file) to a text file containing the prompt.
    """
    suite_path = Path(path).resolve()
    base = suite_path.parent
    data = yaml.safe_load(suite_path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError(f"{path}: suite must be a YAML mapping")
    if "prompts" not in data or not data["prompts"]:
        raise ValueError(f"{path}: 'prompts' section is required")
    if "cases" not in data or not data["cases"]:
        raise ValueError(f"{path}: 'cases' section is required")

    prompts: Dict[str, str] = {}
    for name, value in data["prompts"].items():
        candidate = base / str(value)
        if candidate.is_file():
            prompts[name] = candidate.read_text(encoding="utf-8")
        else:
            prompts[name] = str(value)

    cases: List[Case] = []
    for i, raw in enumerate(data["cases"]):
        name = raw.get("name", f"case-{i + 1}")
        if "input" not in raw:
            raise ValueError(f"{path}: case '{name}' is missing 'input'")
        checks: List[Check] = []
        for chk in raw.get("checks", []):
            if not isinstance(chk, dict) or len(chk) != 1:
                raise ValueError(
                    f"{path}: case '{name}' has a malformed check: {chk!r}"
                )
            ctype, cval = next(iter(chk.items()))
            if ctype not in VALID_CHECKS:
                raise ValueError(
                    f"{path}: case '{name}' uses unknown check '{ctype}'. "
                    f"Valid: {', '.join(sorted(VALID_CHECKS))}"
                )
            checks.append(Check(type=ctype, value=cval))
        if not checks:
            raise ValueError(f"{path}: case '{name}' has no checks")
        cases.append(Case(name=name, input=str(raw["input"]), checks=checks))

    return Suite(
        provider=data.get("provider", "command"),
        model=data.get("model", "claude-opus-4-8"),
        command=data.get("command", ""),
        max_tokens=int(data.get("max_tokens", 4096)),
        prompts=prompts,
        cases=cases,
        base_dir=base,
    )
