from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from anvil.trace import TraceRun


class BenchmarkOutput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    json_path: Path = Field(default=Path("docs/paper/results.json"), alias="json")
    markdown: Path = Path("docs/paper/results.md")


class BenchmarkManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    suites: list[Path] = Field(min_length=1)
    output: BenchmarkOutput = Field(default_factory=BenchmarkOutput)


class BaselineOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    reason: str


class FinalAnswerBaseline:
    failure_terms = (
        "traceback",
        "exception",
        "failed",
        "error:",
        "tool error",
        "protocol error",
    )

    def grade(self, trace: TraceRun) -> BaselineOutcome:
        final_output = (trace.final_output or "").strip()
        if not final_output:
            return BaselineOutcome(passed=False, reason="final output missing")

        lowered = final_output.lower()
        failure_terms = [term for term in self.failure_terms if term in lowered]
        if failure_terms:
            return BaselineOutcome(
                passed=False,
                reason=f"final output contains failure terms: {', '.join(failure_terms)}",
            )

        return BaselineOutcome(passed=True, reason="final answer present without obvious errors")


def load_benchmark_manifest(path: str | Path) -> BenchmarkManifest:
    manifest_path = Path(path)
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest = BenchmarkManifest.model_validate(payload)
    return manifest.model_copy(
        update={
            "suites": [_resolve_manifest_path(manifest_path, suite) for suite in manifest.suites],
            "output": BenchmarkOutput(
                json_path=_resolve_manifest_path(manifest_path, manifest.output.json_path),
                markdown=_resolve_manifest_path(manifest_path, manifest.output.markdown),
            ),
        },
    )


def _resolve_manifest_path(manifest_path: Path, value: Path) -> Path:
    if value.is_absolute():
        return value
    return manifest_path.parent / value
