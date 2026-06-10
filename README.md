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
4. **Deterministic assertions.** No LLM-as-judge flakiness: contains / regex / JSON validity / JSON keys / length / similarity checks that mean the same thing on every run.

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

## CI integration

```yaml
# .github/workflows/prompts.yml
- run: pip install promptdiff
- run: promptdiff run suite.yaml --md >> "$GITHUB_STEP_SUMMARY"
```

Exit codes: `0` all green · `1` failures · `2` regression detected. The cached responses in `.promptdiff/cache/` make this free and deterministic — re-record locally when prompts or cases change.

## License

MIT © [Mohamed Fazil](https://github.com/FaZ07)
