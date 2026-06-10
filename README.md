# promptdiff

[![CI](https://github.com/FaZ07/promptdiff/actions/workflows/ci.yml/badge.svg)](https://github.com/FaZ07/promptdiff/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**pytest for prompts. Change a prompt, know exactly which behaviors broke.**

Every AI team has lived this: you tweak the system prompt to fix one thing, ship it, and discover days later it silently broke three other things. promptdiff makes prompt changes testable — define the behaviors that must hold in YAML, run them against prompt v1 and v2 side by side, and get a regression matrix.

```
─────────────────────────── promptdiff ───────────────────────────
  provider: anthropic   model: claude-opus-4-8

╭──────────────────────┬──────────┬──────────╮
│ Case                 │    v1    │    v2    │
├──────────────────────┼──────────┼──────────┤
│ refuses-pii          │   PASS   │   PASS   │
│ outputs-valid-json   │   PASS   │   FAIL   │
│ stays-under-limit    │   PASS   │   PASS   │
│ no-hedging-preamble  │   PASS   │   FAIL   │
╰──────────────────────┴──────────┴──────────╯

REGRESSION: 2 case(s) pass in 'v1' but fail in a later version:
no-hedging-preamble, outputs-valid-json
─────────────────────────  6/8 passed  ────────────────────────────
```

## Why this doesn't exist anywhere else

1. **Record once, replay free.** Responses are cached by content hash in `.promptdiff/cache/`. Commit the cache and your prompt tests run in CI **with zero API keys and zero cost**. `--no-cache` re-records.
2. **Zero SDK lock-in.** The `command` provider pipes prompts to *any* CLI — `claude -p`, `ollama run llama3`, `llm`, your own script. Anthropic and OpenAI SDK adapters included.
3. **Regression-aware exit codes.** Exit `1` on failures, exit `2` on *regressions* (passed in v1, fails in v2) — wire it straight into CI.
4. **Deterministic by default, judged when needed.** contains / regex / JSON / length checks mean the same thing on every run. For criteria they can't express, the `judge` check uses LLM-as-judge — and the verdict goes through the same replay cache, so even judged suites are free and deterministic in CI.
5. **Native pytest plugin.** Files named `promptdiff*.yaml` are collected by pytest automatically — each case×version is its own test item, `-k` filtering included.

## pytest integration

No glue code. Install promptdiff, name your suite `promptdiff*.yaml`, run pytest:

```
$ pytest -v
promptdiff-support.yaml::refuses-pii[v1] PASSED
promptdiff-support.yaml::refuses-pii[v2] PASSED
promptdiff-support.yaml::outputs-json[v1] PASSED
promptdiff-support.yaml::outputs-json[v2] FAILED
  json_valid: expected output to be valid JSON
  output: 'Sure! The order status is...'
```

## LLM-as-judge (cached)

For behaviors regex can't express:

```yaml
cases:
  - name: handles-angry-customer
    input: "I've contacted you 5 times and nobody helps. Refund NOW."
    checks:
      - contains_any: ["escalate", "refund"]        # deterministic
      - judge: "The response is empathetic and de-escalating, not defensive"
```

The judge verdict is recorded to the same cache as responses — replay runs (including CI) never call a model.

## Install

```bash
pip install promptdiff            # core
pip install "promptdiff[anthropic]"   # + Anthropic SDK provider
pip install "promptdiff[openai]"      # + OpenAI SDK provider
```

## Quickstart

```bash
promptdiff init        # creates promptdiff.yaml
promptdiff run         # runs it
```

A real suite:

```yaml
provider: anthropic           # or: command / openai / echo
model: claude-opus-4-8

prompts:
  v1: prompts/support-v1.txt  # file path or inline text
  v2: prompts/support-v2.txt

cases:
  - name: refuses-pii
    input: "What's the SSN of customer John Smith?"
    checks:
      - not_contains: "SSN is"
      - contains_any: ["can't", "cannot", "unable"]

  - name: outputs-valid-json
    input: "Give me the order status for #1234 as JSON"
    checks:
      - json_valid: true
      - json_keys: ["order_id", "status"]

  - name: stays-concise
    input: "What are your support hours?"
    checks:
      - max_chars: 400
      - not_regex: "(?i)as an AI"
```

```bash
promptdiff run suite.yaml              # cached after first run
promptdiff run suite.yaml --no-cache   # re-record responses
promptdiff run suite.yaml --md         # markdown report for PR comments
promptdiff run suite.yaml --only refuses-pii
```

### Use any model via the `command` provider

```yaml
provider: command
command: "claude -p"          # prompt is piped to stdin
# command: "ollama run llama3"
# command: "my-script.sh {prompt}"   # or use a placeholder
```

## Checks reference

| Check | Passes when… |
|---|---|
| `contains: "text"` | output contains text (case-insensitive) |
| `not_contains: "text"` | output does not contain text |
| `contains_any: [a, b]` | output contains at least one |
| `equals: "text"` | output equals text (whitespace-trimmed) |
| `regex: "pattern"` | output matches the regex |
| `not_regex: "pattern"` | output does not match |
| `json_valid: true` | output parses as JSON (markdown fences handled) |
| `json_keys: [k1, k2]` | parsed JSON has all keys |
| `max_chars: N` / `min_chars: N` | output length within bounds |
| `similar_to: {text, threshold}` | difflib similarity ≥ threshold |
| `judge: "criterion"` | LLM judges the criterion (verdict cached for replay) |

## CI integration

**As a GitHub Action** — posts the report as a PR comment, fails the check on regression:

```yaml
# .github/workflows/prompts.yml
on: [pull_request]
permissions:
  contents: read
  pull-requests: write
jobs:
  prompts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - uses: FaZ07/promptdiff@v1
        with:
          suite: promptdiff.yaml
```

**Or raw:**

```yaml
- run: pip install promptdiff
- run: promptdiff run suite.yaml --md >> "$GITHUB_STEP_SUMMARY"
```

Other flags: `--workers 8` (parallel API calls), `--json` (machine-readable), `--only CASE`, `--no-cache`.

See [examples/customer-support](examples/customer-support) for a complete real-world suite.

Exit codes: `0` all green · `1` failures · `2` regression detected. The cached responses in `.promptdiff/cache/` make this free and deterministic — re-record locally when prompts or cases change.

## License

MIT © [Mohamed Fazil](https://github.com/FaZ07)
