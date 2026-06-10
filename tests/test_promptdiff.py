import textwrap
from pathlib import Path

import pytest

from promptdiff import checks as checks_mod
from promptdiff import runner, spec
from promptdiff.report import to_markdown
from promptdiff.spec import Check


# ── checks ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ctype,value,output,expected", [
    ("contains", "hello", "Hello World", True),
    ("contains", "absent", "Hello World", False),
    ("not_contains", "ssn", "I cannot share that", True),
    ("not_contains", "cannot", "I cannot share that", False),
    ("contains_any", ["yes", "sure"], "Sure, here it is", True),
    ("contains_any", ["no", "never"], "Sure, here it is", False),
    ("equals", "42", "  42  ", True),
    ("regex", r"\d{3}-\d{4}", "call 555-1234", True),
    ("not_regex", r"\d{3}-\d{4}", "no numbers here", True),
    ("max_chars", 10, "short", True),
    ("max_chars", 3, "too long", False),
    ("min_chars", 3, "long enough", True),
    ("json_valid", True, '{"a": 1}', True),
    ("json_valid", True, "not json at all", False),
    ("json_keys", ["name", "age"], '{"name": "x", "age": 1}', True),
    ("json_keys", ["missing"], '{"name": "x"}', False),
])
def test_checks(ctype, value, output, expected):
    ok, _ = checks_mod.run_check(Check(type=ctype, value=value), output)
    assert ok is expected


def test_json_extraction_from_markdown_fence():
    output = 'Here you go:\n```json\n{"key": "value"}\n```\nDone!'
    ok, _ = checks_mod.run_check(Check(type="json_valid", value=True), output)
    assert ok


def test_similar_to():
    ok, _ = checks_mod.run_check(
        Check(type="similar_to", value={"text": "hello world", "threshold": 0.8}),
        "hello world!",
    )
    assert ok


# ── spec loading ──────────────────────────────────────────────────────────────

def _write_suite(tmp_path: Path, body: str) -> Path:
    f = tmp_path / "suite.yaml"
    f.write_text(textwrap.dedent(body), encoding="utf-8")
    return f


def test_load_suite(tmp_path):
    f = _write_suite(tmp_path, """
        provider: echo
        prompts:
          v1: "Be helpful."
        cases:
          - name: t1
            input: "hi"
            checks:
              - contains: "hi"
    """)
    suite = spec.load(str(f))
    assert suite.provider == "echo"
    assert suite.prompts["v1"] == "Be helpful."
    assert suite.cases[0].name == "t1"


def test_load_prompt_from_file(tmp_path):
    (tmp_path / "p.txt").write_text("File-based prompt")
    f = _write_suite(tmp_path, """
        provider: echo
        prompts:
          v1: p.txt
        cases:
          - input: "x"
            checks: [{contains: "x"}]
    """)
    suite = spec.load(str(f))
    assert suite.prompts["v1"] == "File-based prompt"


def test_unknown_check_rejected(tmp_path):
    f = _write_suite(tmp_path, """
        prompts: {v1: "p"}
        cases:
          - input: "x"
            checks: [{bogus_check: "y"}]
    """)
    with pytest.raises(ValueError, match="unknown check"):
        spec.load(str(f))


# ── runner + cache ────────────────────────────────────────────────────────────

def _echo_suite(tmp_path) -> spec.Suite:
    f = _write_suite(tmp_path, """
        provider: echo
        prompts:
          plain: "Just echo."
          shouty: "Respond in UPPERCASE."
        cases:
          - name: lowercase-ok
            input: "hello"
            checks:
              - contains: "hello"
          - name: must-be-loud
            input: "hello"
            checks:
              - regex: "HELLO"
    """)
    return spec.load(str(f))


def test_run_matrix_and_regression(tmp_path):
    suite = _echo_suite(tmp_path)
    result = runner.run(suite)
    assert len(result.results) == 4  # 2 versions x 2 cases
    by = {(r.case, r.version): r.passed for r in result.results}
    assert by[("lowercase-ok", "plain")] is True
    assert by[("must-be-loud", "plain")] is False   # echo doesn't uppercase
    assert by[("must-be-loud", "shouty")] is True   # UPPERCASE applied
    # 'lowercase-ok' passes in both -> contains check is case-insensitive
    assert by[("lowercase-ok", "shouty")] is True


def test_cache_replay(tmp_path):
    suite = _echo_suite(tmp_path)
    first = runner.run(suite)
    # First result per (version, input) is fresh; identical case inputs
    # within the run legitimately dedupe via the cache.
    assert not first.results[0].cached
    second = runner.run(suite)
    assert all(r.cached for r in second.results)
    fresh = runner.run(suite, use_cache=False)
    assert all(not r.cached for r in fresh.results)


def test_regression_detection(tmp_path):
    f = _write_suite(tmp_path, """
        provider: echo
        prompts:
          v1: "Just echo."
          v2: "Respond in JSON."
        cases:
          - name: plain-text
            input: "hello"
            checks:
              - equals: "hello"
    """)
    suite = spec.load(str(f))
    result = runner.run(suite)
    assert result.regressions() == ["plain-text"]  # v2 wraps in JSON, breaking equals


def test_markdown_report(tmp_path):
    suite = _echo_suite(tmp_path)
    md = to_markdown(runner.run(suite))
    assert "promptdiff" in md
    assert "| Case |" in md
    assert "must-be-loud" in md


def test_parallel_matches_serial(tmp_path):
    suite = _echo_suite(tmp_path)
    serial = runner.run(suite, use_cache=False)
    parallel = runner.run(suite, use_cache=False, workers=4)
    assert [(r.case, r.version, r.passed) for r in serial.results] == \
           [(r.case, r.version, r.passed) for r in parallel.results]


def test_judge_check(tmp_path, monkeypatch):
    f = _write_suite(tmp_path, """
        provider: echo
        prompts: {v1: "p"}
        cases:
          - name: judged
            input: "hello"
            checks:
              - judge: "response is friendly"
    """)
    suite = spec.load(str(f))

    def fake_provider(system, user_input):
        if "evaluator" in system:
            return "PASS - response is friendly enough."
        return "hi there!"

    monkeypatch.setattr(runner, "get_provider", lambda s: fake_provider)
    result = runner.run(suite)
    assert result.results[0].passed
    assert "judge" in result.results[0].checks[0].type


def test_judge_fail_verdict(tmp_path, monkeypatch):
    f = _write_suite(tmp_path, """
        provider: echo
        prompts: {v1: "p"}
        cases:
          - name: judged
            input: "hello"
            checks:
              - judge: "response is in French"
    """)
    suite = spec.load(str(f))
    monkeypatch.setattr(
        runner, "get_provider",
        lambda s: lambda sys_p, inp: "FAIL - the response is English.",
    )
    result = runner.run(suite)
    assert not result.results[0].passed


def test_pytest_plugin_collects(tmp_path, pytester=None):
    # Plugin registration smoke test: the entry point module imports
    # and exposes the collect hook.
    from promptdiff import pytest_plugin
    assert hasattr(pytest_plugin, "pytest_collect_file")
