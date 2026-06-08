from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from anvil.clustering import FailureCluster
from anvil.flakiness import detect_flaky_scenarios
from anvil.grading import GradeResult
from anvil.trace import TraceRun

RESULTS_SCHEMA_VERSION = "anvil.results.v1"
RUN_MANIFEST_SCHEMA_VERSION = "anvil.run_manifest.v1"


class ResultsArtifactError(ValueError):
    pass


class RunManifestError(ValueError):
    pass


class RunManifestFilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class RunManifestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["anvil.run_manifest.v1"] = RUN_MANIFEST_SCHEMA_VERSION
    run_id: str
    generated_at: datetime
    files: list[RunManifestFilePayload]


class ResultsFlakyScenarioPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    passed_trials: int
    failed_trials: int
    total_trials: int
    pass_rate: float


class ResultsSummaryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_scenarios: int
    total_trials: int
    passed_trials: int
    failed_trials: int
    pass_rate: float
    flaky_scenarios: list[ResultsFlakyScenarioPayload]


class ResultsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["anvil.results.v1"] = RESULTS_SCHEMA_VERSION
    suite: str
    run_id: str
    summary: ResultsSummaryPayload
    grades: list[GradeResult]
    clusters: list[FailureCluster]


def create_run_id(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%d_%H%M%S")
    return f"run_{timestamp}"


def create_run_dir(runs_dir: str | Path, run_id: str | None = None) -> Path:
    root = Path(runs_dir)
    root.mkdir(parents=True, exist_ok=True)
    selected_id = run_id or create_run_id()
    run_dir = root / selected_id
    suffix = 1
    while run_dir.exists():
        run_dir = root / f"{selected_id}_{suffix}"
        suffix += 1
    (run_dir / "traces").mkdir(parents=True)
    return run_dir


def write_trace(run_dir: Path, trace: TraceRun) -> Path:
    trace_path = run_dir / "traces" / f"{trace.scenario_id}_trial_{trace.trial}.json"
    trace_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    return trace_path


def write_results(
    *,
    run_dir: Path,
    suite_name: str,
    run_id: str,
    total_scenarios: int,
    grades: list[GradeResult],
    clusters: list[FailureCluster],
) -> Path:
    passed_trials = sum(1 for grade in grades if grade.passed)
    total_trials = len(grades)
    payload = ResultsPayload(
        suite=suite_name,
        run_id=run_id,
        summary=ResultsSummaryPayload(
            total_scenarios=total_scenarios,
            total_trials=total_trials,
            passed_trials=passed_trials,
            failed_trials=total_trials - passed_trials,
            pass_rate=round((passed_trials / total_trials * 100) if total_trials else 0.0, 1),
            flaky_scenarios=[
                ResultsFlakyScenarioPayload.model_validate(scenario.to_json())
                for scenario in detect_flaky_scenarios(grades)
            ],
        ),
        grades=grades,
        clusters=clusters,
    ).model_dump(mode="json")
    results_path = run_dir / "results.json"
    results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return results_path


def write_run_manifest(run_dir: str | Path, *, run_id: str) -> Path:
    selected_run_dir = Path(run_dir)
    files = [
        RunManifestFilePayload(
            path=_manifest_path(selected_run_dir, artifact),
            sha256=_sha256_file(artifact),
            size_bytes=artifact.stat().st_size,
        )
        for artifact in _run_manifest_artifacts(selected_run_dir)
    ]
    payload = RunManifestPayload(
        run_id=run_id,
        generated_at=datetime.now(UTC),
        files=files,
    ).model_dump(mode="json")
    manifest_path = selected_run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def validate_run_manifest(run_dir: str | Path) -> dict[str, Any] | None:
    selected_run_dir = Path(run_dir)
    manifest_path = selected_run_dir / "manifest.json"
    if not manifest_path.exists():
        return None

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as error:
        msg = f"could not read run manifest {manifest_path}: {error}"
        raise RunManifestError(msg) from error
    except json.JSONDecodeError as error:
        msg = f"could not parse run manifest {manifest_path} as JSON: {error}"
        raise RunManifestError(msg) from error
    if not isinstance(payload, dict):
        msg = f"run manifest {manifest_path} did not contain a JSON object"
        raise RunManifestError(msg)

    try:
        manifest = RunManifestPayload.model_validate(payload)
    except ValidationError as error:
        msg = f"run manifest {manifest_path} did not match {RUN_MANIFEST_SCHEMA_VERSION}: {error}"
        raise RunManifestError(msg) from error

    for file_payload in manifest.files:
        artifact_path = _manifest_artifact_path(selected_run_dir, file_payload.path)
        if not artifact_path.is_file():
            msg = f"manifest file missing: {file_payload.path}"
            raise RunManifestError(msg)
        actual_sha256 = _sha256_file(artifact_path)
        if actual_sha256 != file_payload.sha256:
            msg = (
                f"manifest hash mismatch for {file_payload.path}: "
                f"expected {file_payload.sha256}, got {actual_sha256}"
            )
            raise RunManifestError(msg)
        actual_size = artifact_path.stat().st_size
        if actual_size != file_payload.size_bytes:
            msg = (
                f"manifest size mismatch for {file_payload.path}: "
                f"expected {file_payload.size_bytes}, got {actual_size}"
            )
            raise RunManifestError(msg)

    return cast(dict[str, Any], manifest.model_dump(mode="json"))


def update_latest_link(runs_dir: str | Path, run_dir: Path) -> Path:
    latest = Path(runs_dir) / "latest"
    if latest.is_symlink() or latest.exists():
        if latest.is_dir() and not latest.is_symlink():
            shutil.rmtree(latest)
        else:
            latest.unlink()
    latest.symlink_to(run_dir.resolve(), target_is_directory=True)
    return latest


def load_results(run_dir: str | Path) -> dict[str, Any]:
    results_path = Path(run_dir) / "results.json"
    try:
        payload = json.loads(results_path.read_text(encoding="utf-8"))
    except OSError as error:
        msg = f"could not read results artifact {results_path}: {error}"
        raise ResultsArtifactError(msg) from error
    except json.JSONDecodeError as error:
        msg = f"could not parse results artifact {results_path} as JSON: {error}"
        raise ResultsArtifactError(msg) from error

    if not isinstance(payload, dict):
        msg = f"results artifact {results_path} did not contain a JSON object"
        raise ResultsArtifactError(msg)

    return _validated_results_payload(results_path, cast(dict[str, Any], payload))


def _validated_results_payload(
    results_path: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    schema_version = payload.get("schema_version")
    if schema_version is None:
        return payload
    if schema_version != RESULTS_SCHEMA_VERSION:
        msg = f"results artifact {results_path} uses unsupported schema_version {schema_version!r}"
        raise ResultsArtifactError(msg)
    try:
        validated = ResultsPayload.model_validate(payload)
    except ValidationError as error:
        msg = f"results artifact {results_path} did not match {RESULTS_SCHEMA_VERSION}: {error}"
        raise ResultsArtifactError(msg) from error
    return cast(dict[str, Any], validated.model_dump(mode="json"))


def _run_manifest_artifacts(run_dir: Path) -> list[Path]:
    artifacts = [path for path in (run_dir / "traces").glob("*.json") if path.is_file()]
    artifacts.extend(
        path for path in [run_dir / "report.md", run_dir / "results.json"] if path.is_file()
    )
    return sorted(artifacts, key=lambda path: _manifest_path(run_dir, path))


def _manifest_path(run_dir: Path, path: Path) -> str:
    return path.relative_to(run_dir).as_posix()


def _manifest_artifact_path(run_dir: Path, path: str) -> Path:
    manifest_path = Path(path)
    if manifest_path.is_absolute():
        msg = f"manifest path escapes run directory: {path}"
        raise RunManifestError(msg)

    run_root = run_dir.resolve()
    artifact_path = (run_dir / manifest_path).resolve()
    try:
        artifact_path.relative_to(run_root)
    except ValueError as error:
        msg = f"manifest path escapes run directory: {path}"
        raise RunManifestError(msg) from error
    return artifact_path


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
