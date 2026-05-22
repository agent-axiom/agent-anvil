from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from anvil.benchmark import (
    BenchmarkAblationResult,
    BenchmarkResult,
    load_benchmark_manifest,
)

LEADERBOARD_SCHEMA_VERSION = "agent-anvil.leaderboard.v1"


class LeaderboardSubmitter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1)
    agent_version: str = ""
    repo_url: str = ""
    commit_sha: str = ""
    notes: str = ""


class LeaderboardBenchmark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    manifest_path: str
    manifest_sha256: str
    scenario_hashes: dict[str, str]


class LeaderboardMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_suites: int
    total_trials: int
    final_answer_pass_rate: float
    final_answer_pass_rate_ci_low: float
    final_answer_pass_rate_ci_high: float
    trace_aware_pass_rate: float
    trace_aware_pass_rate_ci_low: float
    trace_aware_pass_rate_ci_high: float
    answer_only_missed_failures: int
    answer_only_missed_failure_rate: float
    answer_only_missed_failure_rate_ci_low: float
    answer_only_missed_failure_rate_ci_high: float
    outcome_counts: dict[str, int]


class LeaderboardArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results_json_path: str
    results_json_sha256: str
    results_markdown_path: str | None = None
    results_markdown_sha256: str | None = None
    table_hashes: dict[str, str] = Field(default_factory=dict)


class LeaderboardVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trust_level: Literal["self_reported", "github_actions", "maintainer_rerun"]
    evidence_sha256: str
    generated_at: str
    generated_by: str
    github_repository: str = ""
    github_sha: str = ""
    github_run_url: str = ""


class LeaderboardSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["agent-anvil.leaderboard.v1"]
    submitter: LeaderboardSubmitter
    benchmark: LeaderboardBenchmark
    metrics: LeaderboardMetrics
    evaluator_ablation: list[BenchmarkAblationResult]
    artifacts: LeaderboardArtifacts
    verification: LeaderboardVerification


class LeaderboardValidationError(ValueError):
    """Raised when a leaderboard submission cannot be verified locally."""


def export_leaderboard_submission(
    *,
    results_json: str | Path,
    manifest_path: str | Path,
    out_path: str | Path,
    agent_name: str,
    agent_version: str = "",
    repo_url: str = "",
    commit_sha: str = "",
    notes: str = "",
) -> LeaderboardSubmission:
    selected_results_json = Path(results_json)
    selected_manifest_path = Path(manifest_path)
    selected_out_path = Path(out_path)
    result = BenchmarkResult.model_validate_json(selected_results_json.read_text(encoding="utf-8"))
    manifest = load_benchmark_manifest(selected_manifest_path)
    artifacts = _artifacts(
        results_json=selected_results_json,
        results_markdown=manifest.output.markdown,
        tables_dir=manifest.output.tables,
    )
    benchmark = LeaderboardBenchmark(
        name=result.name,
        description=result.description,
        manifest_path=str(_display_path(selected_manifest_path)),
        manifest_sha256=_sha256_file(selected_manifest_path),
        scenario_hashes={
            str(_display_path(scenario_path)): _sha256_file(scenario_path)
            for scenario_path in manifest.suites
        },
    )
    metrics = LeaderboardMetrics(
        total_suites=result.total_suites,
        total_trials=result.total_trials,
        final_answer_pass_rate=result.final_answer_pass_rate,
        final_answer_pass_rate_ci_low=result.final_answer_pass_rate_ci_low,
        final_answer_pass_rate_ci_high=result.final_answer_pass_rate_ci_high,
        trace_aware_pass_rate=result.trace_aware_pass_rate,
        trace_aware_pass_rate_ci_low=result.trace_aware_pass_rate_ci_low,
        trace_aware_pass_rate_ci_high=result.trace_aware_pass_rate_ci_high,
        answer_only_missed_failures=result.answer_only_missed_failures,
        answer_only_missed_failure_rate=result.answer_only_missed_failure_rate,
        answer_only_missed_failure_rate_ci_low=result.answer_only_missed_failure_rate_ci_low,
        answer_only_missed_failure_rate_ci_high=result.answer_only_missed_failure_rate_ci_high,
        outcome_counts=result.outcome_counts,
    )
    submitter = LeaderboardSubmitter(
        agent_name=agent_name,
        agent_version=agent_version,
        repo_url=repo_url,
        commit_sha=commit_sha or os.getenv("GITHUB_SHA", ""),
        notes=notes,
    )
    verification = _verification(
        submitter=submitter,
        benchmark=benchmark,
        metrics=metrics,
        artifacts=artifacts,
        evaluator_ablation=result.evaluator_ablation,
    )
    submission = LeaderboardSubmission(
        schema_version=LEADERBOARD_SCHEMA_VERSION,
        submitter=submitter,
        benchmark=benchmark,
        metrics=metrics,
        evaluator_ablation=result.evaluator_ablation,
        artifacts=artifacts,
        verification=verification,
    )

    selected_out_path.parent.mkdir(parents=True, exist_ok=True)
    selected_out_path.write_text(
        submission.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return submission


def validate_leaderboard_submission(
    submission_path: str | Path,
    *,
    verify_artifacts: bool = True,
    require_trust_level: str | None = None,
) -> LeaderboardSubmission:
    selected_submission_path = Path(submission_path)
    submission = LeaderboardSubmission.model_validate_json(
        selected_submission_path.read_text(encoding="utf-8")
    )
    if require_trust_level and submission.verification.trust_level != require_trust_level:
        raise LeaderboardValidationError(
            "trust level mismatch: "
            f"expected {require_trust_level}, got {submission.verification.trust_level}"
        )

    expected_evidence_hash = _evidence_sha256(submission)
    if expected_evidence_hash != submission.verification.evidence_sha256:
        raise LeaderboardValidationError(
            "evidence hash mismatch: "
            f"expected {expected_evidence_hash}, "
            f"got {submission.verification.evidence_sha256}"
        )

    if verify_artifacts:
        _validate_artifact_hashes(submission)

    return submission


def _evidence_sha256(submission: LeaderboardSubmission) -> str:
    evidence_payload = {
        "submitter": submission.submitter.model_dump(mode="json"),
        "benchmark": submission.benchmark.model_dump(mode="json"),
        "metrics": submission.metrics.model_dump(mode="json"),
        "artifacts": submission.artifacts.model_dump(mode="json"),
        "evaluator_ablation": [
            entry.model_dump(mode="json") for entry in submission.evaluator_ablation
        ],
    }
    return _sha256_json(evidence_payload)


def _validate_artifact_hashes(submission: LeaderboardSubmission) -> None:
    _validate_file_hash(
        submission.benchmark.manifest_path,
        submission.benchmark.manifest_sha256,
        label="benchmark manifest",
    )
    for scenario_path, expected_hash in submission.benchmark.scenario_hashes.items():
        _validate_file_hash(scenario_path, expected_hash, label=f"scenario {scenario_path}")
    _validate_file_hash(
        submission.artifacts.results_json_path,
        submission.artifacts.results_json_sha256,
        label="results JSON",
    )
    if submission.artifacts.results_markdown_path and submission.artifacts.results_markdown_sha256:
        _validate_file_hash(
            submission.artifacts.results_markdown_path,
            submission.artifacts.results_markdown_sha256,
            label="results Markdown",
        )
    for artifact_path, expected_hash in submission.artifacts.table_hashes.items():
        _validate_file_hash(artifact_path, expected_hash, label=f"table artifact {artifact_path}")


def _validate_file_hash(path_text: str, expected_hash: str, *, label: str) -> None:
    path = Path(path_text)
    if not path.exists():
        raise LeaderboardValidationError(f"artifact missing: {label} at {path_text}")
    actual_hash = _sha256_file(path)
    if actual_hash != expected_hash:
        raise LeaderboardValidationError(
            f"artifact hash mismatch for {label}: expected {expected_hash}, got {actual_hash}"
        )


def _artifacts(
    *,
    results_json: Path,
    results_markdown: Path,
    tables_dir: Path,
) -> LeaderboardArtifacts:
    table_hashes: dict[str, str] = {}
    if tables_dir.exists():
        table_hashes = {
            str(_display_path(path)): _sha256_file(path)
            for path in sorted(tables_dir.iterdir())
            if path.is_file()
        }
    return LeaderboardArtifacts(
        results_json_path=str(_display_path(results_json)),
        results_json_sha256=_sha256_file(results_json),
        results_markdown_path=str(_display_path(results_markdown))
        if results_markdown.exists()
        else None,
        results_markdown_sha256=_sha256_file(results_markdown)
        if results_markdown.exists()
        else None,
        table_hashes=table_hashes,
    )


def _verification(
    *,
    submitter: LeaderboardSubmitter,
    benchmark: LeaderboardBenchmark,
    metrics: LeaderboardMetrics,
    artifacts: LeaderboardArtifacts,
    evaluator_ablation: list[BenchmarkAblationResult],
) -> LeaderboardVerification:
    evidence_payload = {
        "submitter": submitter.model_dump(mode="json"),
        "benchmark": benchmark.model_dump(mode="json"),
        "metrics": metrics.model_dump(mode="json"),
        "artifacts": artifacts.model_dump(mode="json"),
        "evaluator_ablation": [entry.model_dump(mode="json") for entry in evaluator_ablation],
    }
    github_run_url = _github_run_url()
    return LeaderboardVerification(
        trust_level="github_actions" if github_run_url else "self_reported",
        evidence_sha256=_sha256_json(evidence_payload),
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        generated_by=f"agent-anvil/{_anvil_version()}",
        github_repository=os.getenv("GITHUB_REPOSITORY", ""),
        github_sha=os.getenv("GITHUB_SHA", ""),
        github_run_url=github_run_url,
    )


def _github_run_url() -> str:
    if os.getenv("GITHUB_ACTIONS") != "true":
        return ""
    server_url = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    repository = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if not repository or not run_id:
        return ""
    return f"{server_url}/{repository}/actions/runs/{run_id}"


def _anvil_version() -> str:
    try:
        return version("agent-anvil")
    except PackageNotFoundError:
        return "0+unknown"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _display_path(path: Path) -> Path:
    try:
        return path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return path
