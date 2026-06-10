"""pytest integration: suites named promptdiff*.yaml are collected as tests.

    pytest                       # runs promptdiff.yaml suites alongside unit tests
    pytest promptdiff-api.yaml   # run one suite directly

Each (case, prompt-version) pair becomes one pytest test item, so failures
show up individually in CI summaries and -k filtering works:

    pytest -k "refuses-pii"
"""

from typing import Optional

import pytest


def pytest_collect_file(parent, file_path) -> Optional["PromptdiffFile"]:
    if file_path.suffix in (".yaml", ".yml") and file_path.name.startswith("promptdiff"):
        return PromptdiffFile.from_parent(parent, path=file_path)
    return None


class PromptdiffFile(pytest.File):
    def collect(self):
        from . import runner, spec

        suite = spec.load(str(self.path))
        result = runner.run(suite)
        for r in result.results:
            yield PromptdiffItem.from_parent(
                self, name=f"{r.case}[{r.version}]", result=r,
            )


class PromptdiffFailure(AssertionError):
    pass


class PromptdiffItem(pytest.Item):
    def __init__(self, *, result, **kwargs):
        super().__init__(**kwargs)
        self.result = result

    def runtest(self) -> None:
        r = self.result
        if r.passed:
            return
        if r.error:
            raise PromptdiffFailure(f"provider error: {r.error}")
        failed = [f"{c.type}: {c.detail}" for c in r.checks if not c.passed]
        output_preview = r.output[:300].replace("\n", " ")
        raise PromptdiffFailure(
            "\n".join(failed) + f"\noutput: {output_preview!r}"
        )

    def repr_failure(self, excinfo):
        if isinstance(excinfo.value, PromptdiffFailure):
            return str(excinfo.value)
        return super().repr_failure(excinfo)

    def reportinfo(self):
        return self.path, 0, self.name
