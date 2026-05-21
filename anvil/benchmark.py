from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


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
