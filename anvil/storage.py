from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from anvil.clustering import FailureCluster
from anvil.flakiness import detect_flaky_scenarios
from anvil.grading import GradeResult
from anvil.trace import TraceRun

RESULTS_SCHEMA_VERSION = "anvil.results.v1"


class ResultsArtifactError(ValueError):
    pass


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
