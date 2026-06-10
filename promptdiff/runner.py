"""Test runner with record/replay caching.

The cache is the feature that makes promptdiff CI-friendly: the first run
records real model responses to .promptdiff/cache/; every later run replays
them for free. Commit the cache to git and your prompt tests run in CI with
zero API keys and zero cost. Use --no-cache to force fresh responses.
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import checks as checks_mod
from .providers import get_provider
from .spec import Case, Suite

CACHE_DIR = ".promptdiff/cache"


@dataclass
class CheckResult:
    type: str
    passed: bool
    detail: str


@dataclass
class CaseResult:
    case: str
    version: str
    passed: bool
    output: str
    checks: List[CheckResult] = field(default_factory=list)
    error: str = ""
    cached: bool = False


@dataclass
class RunResult:
    suite_provider: str
    model: str
    versions: List[str]
    results: List[CaseResult]

    def for_version(self, version: str) -> List[CaseResult]:
        return [r for r in self.results if r.version == version]

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def regressions(self) -> List[str]:
        """Case names that pass in the first version but fail in a later one."""
        if len(self.versions) < 2:
            return []
        baseline = {r.case: r.passed for r in self.for_version(self.versions[0])}
        regressed = set()
        for v in self.versions[1:]:
            for r in self.for_version(v):
                if baseline.get(r.case) and not r.passed:
                    regressed.add(r.case)
        return sorted(regressed)


def run(suite: Suite, use_cache: bool = True, only: Optional[str] = None) -> RunResult:
    """Execute every case against every prompt version."""
    provider = get_provider(suite)
    cache_root = suite.base_dir / CACHE_DIR
    cases = [c for c in suite.cases if only is None or c.name == only]
    results: List[CaseResult] = []

    for version, prompt_text in suite.prompts.items():
        for case in cases:
            results.append(
                _run_case(suite, provider, cache_root, version, prompt_text, case, use_cache)
            )

    return RunResult(
        suite_provider=suite.provider,
        model=suite.model,
        versions=list(suite.prompts.keys()),
        results=results,
    )


def _cache_key(suite: Suite, prompt: str, user_input: str) -> str:
    raw = f"{suite.provider}|{suite.model}|{prompt}|{user_input}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _run_case(suite, provider, cache_root: Path, version: str,
              prompt_text: str, case: Case, use_cache: bool) -> CaseResult:
    key = _cache_key(suite, prompt_text, case.input)
    cache_file = cache_root / f"{key}.txt"

    cached = False
    try:
        if use_cache and cache_file.is_file():
            output = cache_file.read_text(encoding="utf-8")
            cached = True
        else:
            output = provider(prompt_text, case.input)
            cache_root.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(output, encoding="utf-8")
    except Exception as e:
        return CaseResult(
            case=case.name, version=version, passed=False,
            output="", error=str(e)[:300],
        )

    check_results = []
    for chk in case.checks:
        ok, detail = checks_mod.run_check(chk, output)
        check_results.append(CheckResult(type=chk.type, passed=ok, detail=detail))

    return CaseResult(
        case=case.name,
        version=version,
        passed=all(c.passed for c in check_results),
        output=output,
        checks=check_results,
        cached=cached,
    )
