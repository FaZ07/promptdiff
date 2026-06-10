"""Provider adapters: turn (system_prompt, user_input) into a model response.

Built-in providers:
- echo:      deterministic, for testing promptdiff itself (no model)
- command:   any shell command (claude CLI, ollama, llm, ...) — zero SDK lock-in
- anthropic: official Anthropic SDK (pip install anthropic)
- openai:    official OpenAI SDK (pip install openai)
"""

import shlex
import subprocess
from typing import Callable

from .spec import Suite

ProviderFn = Callable[[str, str], str]


def get_provider(suite: Suite) -> ProviderFn:
    if suite.provider == "echo":
        return _echo
    if suite.provider == "command":
        if not suite.command:
            raise ValueError("provider 'command' requires a 'command:' field in the suite")
        return _make_command(suite.command)
    if suite.provider == "anthropic":
        return _make_anthropic(suite.model, suite.max_tokens)
    if suite.provider == "openai":
        return _make_openai(suite.model, suite.max_tokens)
    raise ValueError(f"unknown provider {suite.provider!r} (valid: echo, command, anthropic, openai)")


def _echo(system: str, user_input: str) -> str:
    """Deterministic provider for self-testing: applies trivial 'instructions'."""
    out = user_input
    if "UPPERCASE" in system:
        out = out.upper()
    if "JSON" in system:
        out = f'{{"echo": "{out}"}}'
    return out


def _make_command(template: str) -> ProviderFn:
    def call(system: str, user_input: str) -> str:
        full_prompt = f"{system}\n\n{user_input}" if system else user_input
        if "{prompt}" in template:
            cmd = template.replace("{prompt}", shlex.quote(full_prompt))
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=300,
            )
        else:
            result = subprocess.run(
                template, shell=True, input=full_prompt,
                capture_output=True, text=True, timeout=300,
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"command provider failed (exit {result.returncode}): {result.stderr[:500]}"
            )
        return result.stdout.strip()
    return call


def _make_anthropic(model: str, max_tokens: int) -> ProviderFn:
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("provider 'anthropic' requires: pip install anthropic") from e

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    def call(system: str, user_input: str) -> str:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system or "You are a helpful assistant.",
            messages=[{"role": "user", "content": user_input}],
        )
        return "".join(b.text for b in response.content if b.type == "text")
    return call


def _make_openai(model: str, max_tokens: int) -> ProviderFn:
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("provider 'openai' requires: pip install openai") from e

    client = OpenAI()  # reads OPENAI_API_KEY from env

    def call(system: str, user_input: str) -> str:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system or "You are a helpful assistant."},
                {"role": "user", "content": user_input},
            ],
        )
        return response.choices[0].message.content or ""
    return call
