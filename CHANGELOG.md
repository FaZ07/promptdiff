# Changelog

## v1.1.0 — 2026-06-10

### Added
- **pytest plugin**: files named `promptdiff*.yaml` are collected by pytest
  automatically; each case×version is an individual test item with `-k`
  filtering and clean failure output
- **`judge` check**: LLM-as-judge for criteria deterministic checks can't
  express; verdicts go through the replay cache so judged suites stay free
  and deterministic in CI
- **GitHub Action** (`FaZ07/promptdiff@v1`): runs the suite on PRs, posts
  the report as a comment, fails the check on regression
- **`--workers N`**: concurrent provider calls for fast real-API runs
- **`--json`**: machine-readable output for tooling
- **examples/customer-support**: complete real-world suite with judge checks

## v1.0.0 — 2026-06-10

- YAML test suites with deterministic checks (contains, regex, json_valid,
  json_keys, length, similarity)
- Side-by-side prompt version matrix with regression detection
- Record/replay cache: run once against a real model, replay free in CI
- Providers: anthropic, openai, any CLI via `command`, echo
- Exit codes: 1 on failure, 2 on regression
- Markdown report mode for PR comments
