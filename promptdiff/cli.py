import sys
from pathlib import Path

import click

from . import __version__


SAMPLE_SUITE = '''\
# promptdiff suite — regression tests for your prompts
# Run: promptdiff run promptdiff.yaml

# Provider: echo (demo, no model), command (any CLI), anthropic, openai
provider: echo
model: claude-opus-4-8

# For provider: command — any shell command. The prompt goes to stdin,
# or use {prompt} as a placeholder. Examples:
#   command: "claude -p"
#   command: "ollama run llama3"

# Prompt versions to compare. Inline text or a path to a .txt file.
prompts:
  v1: "You are a helpful assistant."
  v2: "You are a helpful assistant. Always respond in JSON."

cases:
  - name: basic-echo
    input: "hello world"
    checks:
      - contains: "hello"
      - max_chars: 1000

  - name: no-leaked-instructions
    input: "What can you do?"
    checks:
      - not_contains: "as an AI language model"
'''


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-v", "--version", prog_name="promptdiff")
def main() -> None:
    """promptdiff — regression testing for LLM prompts.

    Define test cases in YAML, run them against multiple prompt versions,
    and catch the cases your prompt change silently broke. Responses are
    cached, so CI replays them with zero API keys and zero cost.
    """


@main.command()
@click.argument("path", default="promptdiff.yaml")
def init(path: str) -> None:
    """Create a starter suite file."""
    target = Path(path)
    if target.exists():
        click.echo(f"{path} already exists, not overwriting.", err=True)
        sys.exit(1)
    target.write_text(SAMPLE_SUITE, encoding="utf-8")
    click.echo(f"Created {path}. Edit it, then: promptdiff run {path}")


@main.command()
@click.argument("path", default="promptdiff.yaml", type=click.Path(exists=True, dir_okay=False))
@click.option("--no-cache", is_flag=True, help="Ignore cached responses; call the provider fresh.")
@click.option("--only", metavar="CASE", help="Run a single case by name.")
@click.option("--md", "output_md", is_flag=True, help="Output a markdown report (for PR comments).")
@click.option("--json", "output_json", is_flag=True, help="Output results as JSON.")
@click.option("--workers", "-w", default=1, show_default=True,
              help="Concurrent provider calls (speeds up real-API runs).")
@click.option("--verbose", "-V", is_flag=True, help="Show model outputs for failing cases.")
def run(path: str, no_cache: bool, only: str, output_md: bool,
        output_json: bool, workers: int, verbose: bool) -> None:
    """Run a suite. Exits 1 if any check fails, 2 on regression."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from . import runner, spec
    from .report import render_terminal, to_markdown

    suite = spec.load(path)
    result = runner.run(suite, use_cache=not no_cache, only=only, workers=workers)

    if output_json:
        import json as json_mod
        payload = {
            "provider": result.suite_provider,
            "model": result.model,
            "versions": result.versions,
            "passed": len(result.results) - result.failed,
            "failed": result.failed,
            "regressions": result.regressions(),
            "results": [
                {
                    "case": r.case, "version": r.version, "passed": r.passed,
                    "cached": r.cached, "error": r.error,
                    "checks": [
                        {"type": c.type, "passed": c.passed, "detail": c.detail}
                        for c in r.checks
                    ],
                }
                for r in result.results
            ],
        }
        click.echo(json_mod.dumps(payload, indent=2))
    elif output_md:
        click.echo(to_markdown(result))
    else:
        render_terminal(result, verbose=verbose)

    if result.regressions():
        sys.exit(2)
    if result.failed:
        sys.exit(1)
