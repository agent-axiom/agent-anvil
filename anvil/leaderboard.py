from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from anvil.benchmark import (
    BenchmarkAblationResult,
    BenchmarkResult,
    load_benchmark_manifest,
)

if TYPE_CHECKING:
    from anvil.attestations import LeaderboardArtifactAttestationVerification

LEADERBOARD_SCHEMA_VERSION = "agent-anvil.leaderboard.v1"
LEADERBOARD_INDEX_SCHEMA_VERSION = "agent-anvil.leaderboard.index.v1"
LEADERBOARD_GITHUB_RUN_VERIFICATION_SCHEMA_VERSION = (
    "agent-anvil.leaderboard.github_run_verification.v1"
)
LEADERBOARD_AUDIT_SCHEMA_VERSION = "agent-anvil.leaderboard.audit.v1"
LEADERBOARD_EVIDENCE_INDEX_SCHEMA_VERSION = "agent-anvil.leaderboard.evidence_index.v1"
LEADERBOARD_MAINTAINER_RERUN_SCHEMA_VERSION = "agent-anvil.leaderboard.maintainer_rerun.v1"


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


class LeaderboardRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    submission_path: str
    submission_schema_version: str
    submission_generated_by: str
    agent_name: str
    agent_version: str
    repo_url: str
    commit_sha: str
    benchmark_name: str
    benchmark_description: str
    benchmark_manifest_sha256: str
    benchmark_scenario_count: int
    trust_level: Literal["self_reported", "github_actions", "maintainer_rerun"]
    evidence_sha256: str
    github_run_url: str
    maintainer_rerun_url: str = ""
    maintainer_rerun_path: str = ""
    maintainer_rerun_evidence_sha256: str = ""
    maintainer_rerun_github_repository: str = ""
    maintainer_rerun_github_sha: str = ""
    maintainer_rerun_generated_at: str = ""
    maintainer_rerun_generated_by: str = ""
    generated_at: str
    total_trials: int
    final_answer_pass_rate: float
    trace_aware_pass_rate: float
    answer_only_missed_failures: int
    answer_only_missed_failure_rate: float
    outcome_counts: dict[str, int]


class LeaderboardIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["agent-anvil.leaderboard.index.v1"]
    generated_at: str
    generated_by: str
    rows: list[LeaderboardRow]


class LeaderboardGithubRunVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["agent-anvil.leaderboard.github_run_verification.v1"]
    status: Literal["verified"]
    submission_path: str
    agent_name: str
    benchmark_name: str
    trust_level: Literal["github_actions"]
    github_repository: str
    github_sha: str
    github_run_url: str
    evidence_sha256: str
    generated_at: str
    generated_by: str


class LeaderboardMaintainerRerun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["agent-anvil.leaderboard.maintainer_rerun.v1"]
    status: Literal["verified"]
    original_evidence_sha256: str = Field(min_length=1)
    rerun_evidence_sha256: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    benchmark_name: str = Field(min_length=1)
    total_trials: int
    final_answer_pass_rate: float
    trace_aware_pass_rate: float
    github_run_url: str = Field(min_length=1)
    github_repository: str = ""
    github_sha: str = ""
    generated_at: str
    generated_by: str
    notes: str = ""


class LeaderboardAuditSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    accept: int
    review: int
    reject: int


class LeaderboardAuditRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_path: str
    decision: Literal["accept", "review", "reject"]
    reason: str
    agent_name: str = ""
    benchmark_name: str = ""
    trust_level: str = ""
    trace_aware_pass_rate: float | None = None
    evidence_sha256: str = ""
    artifact_status: Literal["verified", "not checked", "failed"] = "not checked"
    github_run_status: Literal["verified", "not checked", "failed"] = "not checked"
    artifact_attestation_status: Literal["verified", "not checked", "failed"] = "not checked"
    artifact_attestation_report_path: str = ""
    artifact_attestation_subject_sha256: str = ""
    maintainer_rerun_path: str = ""
    maintainer_rerun_url: str = ""
    maintainer_rerun_evidence_sha256: str = ""


class LeaderboardAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["agent-anvil.leaderboard.audit.v1"]
    generated_at: str
    generated_by: str
    submissions_dir: str
    evidence_index_path: str = ""
    require_artifact_attestation: bool = False
    summary: LeaderboardAuditSummary
    rows: list[LeaderboardAuditRow]
    markdown: str


class LeaderboardEvidenceVerificationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_reports: int
    github_actions: int
    maintainer_rerun: int
    artifact_attestations: int = 0


class LeaderboardEvidenceVerificationRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_path: str
    report_path: str
    report_schema_version: Literal[
        "agent-anvil.leaderboard.github_run_verification.v1",
        "agent-anvil.leaderboard.maintainer_rerun.v1",
    ]
    trust_level: Literal["github_actions", "maintainer_rerun"]
    evidence_sha256: str
    github_run_url: str
    artifact_attestation_report_path: str = ""
    artifact_attestation_subject_sha256: str = ""
    artifact_attestation_github_repository: str = ""
    artifact_attestation_github_sha: str = ""


class LeaderboardEvidenceVerificationIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["agent-anvil.leaderboard.evidence_index.v1"]
    generated_at: str
    generated_by: str
    submissions_dir: str
    reports_dir: str
    summary: LeaderboardEvidenceVerificationSummary
    reports: list[LeaderboardEvidenceVerificationRef]


class LeaderboardValidationError(ValueError):
    """Raised when a leaderboard submission cannot be verified locally."""


@dataclass(frozen=True)
class LeaderboardPrPreparation:
    submission: LeaderboardSubmission
    target_path: Path
    branch_name: str
    commit_message: str
    pr_title: str
    pr_body: str
    next_steps: str


@dataclass(frozen=True)
class LeaderboardInspection:
    submission: LeaderboardSubmission
    artifact_status: Literal["verified", "not checked", "failed"]
    artifact_error: str
    github_run_status: Literal["verified", "not checked", "failed"]
    github_run_error: str
    warnings: tuple[str, ...]
    markdown: str

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


@dataclass(frozen=True)
class LeaderboardReproductionScript:
    submission: LeaderboardSubmission
    path: Path
    content: str


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
    verify_github_run: bool = False,
) -> LeaderboardSubmission:
    selected_submission_path = Path(submission_path)
    submission = _load_leaderboard_submission(selected_submission_path)
    _validate_trust_metadata(submission)
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
    if verify_github_run:
        _validate_github_actions_run(submission)

    return submission


def _load_leaderboard_submission(path: Path) -> LeaderboardSubmission:
    try:
        return LeaderboardSubmission.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise LeaderboardValidationError(
            f"invalid leaderboard submission at {path}: {error}"
        ) from error


def _validate_trust_metadata(submission: LeaderboardSubmission) -> None:
    verification = submission.verification
    if verification.trust_level == "maintainer_rerun":
        raise LeaderboardValidationError(
            "maintainer_rerun trust requires a maintainer rerun attestation; "
            "direct leaderboard submissions may only claim self_reported or github_actions"
        )
    if verification.trust_level != "github_actions":
        return

    required_fields = {
        "verification.github_run_url": verification.github_run_url,
        "verification.github_repository": verification.github_repository,
        "verification.github_sha": verification.github_sha,
    }
    missing = [field for field, value in required_fields.items() if not value.strip()]
    if missing:
        raise LeaderboardValidationError("github_actions trust requires " + ", ".join(missing))

    expected_repo_path = f"/{verification.github_repository}/actions/runs/"
    if expected_repo_path not in verification.github_run_url:
        raise LeaderboardValidationError(
            "github_actions trust requires verification.github_run_url to point to "
            f"verification.github_repository ({verification.github_repository})"
        )

    submitter_sha = submission.submitter.commit_sha.strip()
    github_sha = verification.github_sha.strip()
    if submitter_sha != github_sha:
        raise LeaderboardValidationError(
            "github_actions trust requires submitter.commit_sha to match "
            f"verification.github_sha ({github_sha})"
        )


def _validate_github_actions_run(submission: LeaderboardSubmission) -> None:
    verification = submission.verification
    if verification.trust_level != "github_actions":
        return

    repository, run_id, host = _github_actions_run_reference(verification)
    payload = _fetch_github_actions_run(
        repository,
        run_id,
        token=_github_api_token(),
        host=host,
    )
    run_repository = _github_run_repository(payload)
    if run_repository != verification.github_repository:
        raise LeaderboardValidationError(
            "GitHub Actions run repository mismatch: "
            f"expected {verification.github_repository}, got {run_repository or 'not provided'}"
        )

    head_sha = str(payload.get("head_sha") or "")
    if head_sha != verification.github_sha:
        raise LeaderboardValidationError(
            "GitHub Actions run head_sha mismatch: "
            f"expected {verification.github_sha}, got {head_sha or 'not provided'}"
        )

    status = str(payload.get("status") or "")
    if status != "completed":
        raise LeaderboardValidationError(
            "GitHub Actions run status mismatch: expected completed, "
            f"got {status or 'not provided'}"
        )

    conclusion = str(payload.get("conclusion") or "")
    if conclusion != "success":
        raise LeaderboardValidationError(
            "GitHub Actions run conclusion mismatch: expected success, "
            f"got {conclusion or 'not provided'}"
        )


def _github_actions_run_reference(
    verification: LeaderboardVerification,
) -> tuple[str, str, str]:
    parsed = urlparse(verification.github_run_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise LeaderboardValidationError(
            "github_actions trust requires verification.github_run_url to be an absolute HTTPS URL"
        )
    path_parts = [part for part in parsed.path.strip("/").split("/") if part]
    min_run_path_parts = 5
    if len(path_parts) < min_run_path_parts or path_parts[2:4] != ["actions", "runs"]:
        raise LeaderboardValidationError(
            "github_actions trust requires verification.github_run_url to look like "
            "https://github.com/OWNER/REPO/actions/runs/RUN_ID"
        )
    repository = f"{path_parts[0]}/{path_parts[1]}"
    if repository != verification.github_repository:
        raise LeaderboardValidationError(
            "github_actions trust requires verification.github_run_url to point to "
            f"verification.github_repository ({verification.github_repository})"
        )
    run_id = path_parts[4]
    if not re.fullmatch(r"\d+", run_id):
        raise LeaderboardValidationError(
            "github_actions trust requires verification.github_run_url to include "
            f"a numeric GitHub Actions run id, got {run_id!r}"
        )
    host = parsed.hostname or "github.com"
    return repository, run_id, host


def _fetch_github_actions_run(
    repository: str,
    run_id: str,
    *,
    token: str | None = None,
    host: str = "github.com",
) -> dict[str, Any]:
    api_base = "https://api.github.com" if host == "github.com" else f"https://{host}/api/v3"
    request = Request(
        f"{api_base}/repos/{repository}/actions/runs/{run_id}",
        headers=_github_api_headers(token),
        method="GET",
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:500]
        detail = f"{error.code} {error.reason}"
        if body:
            detail = f"{detail}: {body}"
        raise LeaderboardValidationError(
            f"GitHub Actions run fetch failed for {repository}/actions/runs/{run_id}: {detail}"
        ) from error
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise LeaderboardValidationError(
            f"GitHub Actions run fetch failed for {repository}/actions/runs/{run_id}: {error}"
        ) from error

    if not isinstance(payload, dict):
        raise LeaderboardValidationError(
            f"GitHub Actions run fetch failed for {repository}/actions/runs/{run_id}: "
            "API response was not an object"
        )
    return payload


def _github_api_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "agent-anvil-leaderboard-verifier",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_api_token() -> str | None:
    return os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or None


def _github_run_repository(payload: dict[str, Any]) -> str:
    repository = payload.get("repository")
    if isinstance(repository, dict):
        full_name = repository.get("full_name")
        if isinstance(full_name, str):
            return full_name
    return ""


def inspect_leaderboard_submission(
    submission_path: str | Path,
    *,
    verify_artifacts: bool = True,
    verify_github_run: bool = False,
) -> LeaderboardInspection:
    submission = validate_leaderboard_submission(submission_path, verify_artifacts=False)
    artifact_status: Literal["verified", "not checked", "failed"] = "not checked"
    artifact_error = ""
    if verify_artifacts:
        try:
            _validate_artifact_hashes(submission)
            artifact_status = "verified"
        except LeaderboardValidationError as error:
            artifact_status = "failed"
            artifact_error = str(error)

    github_run_status: Literal["verified", "not checked", "failed"] = "not checked"
    github_run_error = ""
    if verify_github_run:
        try:
            _validate_github_actions_run(submission)
            github_run_status = (
                "verified"
                if submission.verification.trust_level == "github_actions"
                else "not checked"
            )
        except LeaderboardValidationError as error:
            github_run_status = "failed"
            github_run_error = str(error)

    warnings = tuple(
        _inspection_warnings(
            submission,
            artifact_status,
            artifact_error,
            github_run_status,
            github_run_error,
        )
    )
    markdown = _inspection_markdown(
        submission=submission,
        artifact_status=artifact_status,
        artifact_error=artifact_error,
        github_run_status=github_run_status,
        github_run_error=github_run_error,
        warnings=warnings,
    )
    return LeaderboardInspection(
        submission=submission,
        artifact_status=artifact_status,
        artifact_error=artifact_error,
        github_run_status=github_run_status,
        github_run_error=github_run_error,
        warnings=warnings,
        markdown=markdown,
    )


def generate_leaderboard_reproduction_script(
    submission_path: str | Path,
    *,
    out_path: str | Path,
) -> LeaderboardReproductionScript:
    submission = validate_leaderboard_submission(submission_path, verify_artifacts=False)
    if not submission.submitter.repo_url or not submission.submitter.commit_sha:
        raise LeaderboardValidationError(
            "leaderboard reproduction requires repo_url and commit_sha "
            "(submitter.repo_url and submitter.commit_sha)"
        )

    selected_out_path = Path(out_path)
    content = _reproduction_script(
        submission=submission,
        submission_path=Path(submission_path),
    )
    selected_out_path.parent.mkdir(parents=True, exist_ok=True)
    selected_out_path.write_text(content, encoding="utf-8")
    selected_out_path.chmod(0o755)
    return LeaderboardReproductionScript(
        submission=submission,
        path=selected_out_path,
        content=content,
    )


def verify_leaderboard_github_run(
    submission_path: str | Path,
) -> LeaderboardGithubRunVerification:
    selected_submission_path = Path(submission_path)
    submission = validate_leaderboard_submission(
        selected_submission_path,
        verify_artifacts=False,
        require_trust_level="github_actions",
        verify_github_run=True,
    )
    return _github_run_verification_report(selected_submission_path, submission)


def verify_leaderboard_github_runs(
    submissions_dir: str | Path,
    *,
    out_dir: str | Path,
    maintainer_reruns_dir: str | Path | None = None,
    index_path: str | Path | None = None,
    verify_artifact_attestations: bool = False,
) -> list[Path]:
    selected_submissions_dir = Path(submissions_dir)
    selected_out_dir = Path(out_dir)
    submissions = _load_submission_files(
        selected_submissions_dir,
        verify_artifacts=False,
        require_trust_level=None,
        verify_github_run=False,
    )
    maintainer_reruns = _load_maintainer_rerun_attestations(maintainer_reruns_dir)
    used_maintainer_reruns: set[str] = set()
    selected_out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    report_refs: list[LeaderboardEvidenceVerificationRef] = []
    for submission_path, submission in submissions:
        evidence_hash = submission.verification.evidence_sha256
        if evidence_hash in maintainer_reruns:
            attestation_path, attestation = maintainer_reruns[evidence_hash]
            _validate_maintainer_rerun_attestation(
                attestation,
                submission,
                attestation_path=attestation_path,
                verify_github_run=True,
            )
            used_maintainer_reruns.add(evidence_hash)
            report_path = selected_out_dir / f"{submission_path.stem}.maintainer_rerun.json"
            report_path.write_text(attestation.model_dump_json(indent=2), encoding="utf-8")
            written.append(report_path)
            report_refs.append(
                LeaderboardEvidenceVerificationRef(
                    submission_path=str(_display_path(submission_path)),
                    report_path=str(_display_path(report_path)),
                    report_schema_version=LEADERBOARD_MAINTAINER_RERUN_SCHEMA_VERSION,
                    trust_level="maintainer_rerun",
                    evidence_sha256=attestation.original_evidence_sha256,
                    github_run_url=attestation.github_run_url,
                )
            )
            continue
        if submission.verification.trust_level != "github_actions":
            raise LeaderboardValidationError(
                "trust level mismatch: expected github_actions or maintainer rerun "
                f"attestation, got {submission.verification.trust_level}"
            )
        _validate_github_actions_run(submission)
        report = _github_run_verification_report(submission_path, submission)
        report_path = selected_out_dir / f"{submission_path.stem}.github_run_verification.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        written.append(report_path)
        artifact_attestation_report_path = ""
        artifact_attestation_subject_sha256 = ""
        artifact_attestation_github_repository = ""
        artifact_attestation_github_sha = ""
        if verify_artifact_attestations:
            artifact_attestation = _verify_artifact_attestation(submission_path)
            selected_attestation_report_path = (
                selected_out_dir / f"{submission_path.stem}.artifact_attestation_verification.json"
            )
            selected_attestation_report_path.write_text(
                artifact_attestation.model_dump_json(indent=2),
                encoding="utf-8",
            )
            artifact_attestation_report_path = str(_display_path(selected_attestation_report_path))
            artifact_attestation_subject_sha256 = artifact_attestation.subject_sha256
            artifact_attestation_github_repository = artifact_attestation.github_repository
            artifact_attestation_github_sha = artifact_attestation.github_sha
        report_refs.append(
            LeaderboardEvidenceVerificationRef(
                submission_path=str(_display_path(submission_path)),
                report_path=str(_display_path(report_path)),
                report_schema_version=LEADERBOARD_GITHUB_RUN_VERIFICATION_SCHEMA_VERSION,
                trust_level="github_actions",
                evidence_sha256=report.evidence_sha256,
                github_run_url=report.github_run_url,
                artifact_attestation_report_path=artifact_attestation_report_path,
                artifact_attestation_subject_sha256=artifact_attestation_subject_sha256,
                artifact_attestation_github_repository=(artifact_attestation_github_repository),
                artifact_attestation_github_sha=artifact_attestation_github_sha,
            )
        )
    unused_reruns = sorted(set(maintainer_reruns) - used_maintainer_reruns)
    if unused_reruns:
        raise LeaderboardValidationError(
            "maintainer rerun original_evidence_sha256 has no matching submission evidence: "
            + ", ".join(unused_reruns)
        )
    if index_path is not None:
        selected_index_path = Path(index_path)
        selected_index_path.parent.mkdir(parents=True, exist_ok=True)
        selected_index_path.write_text(
            _leaderboard_evidence_index(
                submissions_dir=selected_submissions_dir,
                reports_dir=selected_out_dir,
                report_refs=report_refs,
            ).model_dump_json(indent=2),
            encoding="utf-8",
        )
    return written


def _leaderboard_evidence_index(
    *,
    submissions_dir: Path,
    reports_dir: Path,
    report_refs: list[LeaderboardEvidenceVerificationRef],
) -> LeaderboardEvidenceVerificationIndex:
    github_actions = sum(
        1 for report_ref in report_refs if report_ref.trust_level == "github_actions"
    )
    maintainer_rerun = sum(
        1 for report_ref in report_refs if report_ref.trust_level == "maintainer_rerun"
    )
    artifact_attestations = sum(
        1 for report_ref in report_refs if report_ref.artifact_attestation_report_path
    )
    return LeaderboardEvidenceVerificationIndex(
        schema_version=LEADERBOARD_EVIDENCE_INDEX_SCHEMA_VERSION,
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        generated_by=f"agent-anvil/{_anvil_version()}",
        submissions_dir=str(_display_path(submissions_dir)),
        reports_dir=str(_display_path(reports_dir)),
        summary=LeaderboardEvidenceVerificationSummary(
            total_reports=len(report_refs),
            github_actions=github_actions,
            maintainer_rerun=maintainer_rerun,
            artifact_attestations=artifact_attestations,
        ),
        reports=report_refs,
    )


def _load_verified_evidence_refs(
    evidence_index_path: str | Path | None,
) -> dict[str, LeaderboardEvidenceVerificationRef]:
    if evidence_index_path is None:
        return {}
    selected_path = Path(evidence_index_path)
    try:
        index = LeaderboardEvidenceVerificationIndex.model_validate_json(
            selected_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise LeaderboardValidationError(
            f"invalid leaderboard evidence index at {selected_path}: {error}"
        ) from error
    _validate_evidence_index_summary(index, selected_path)

    refs_by_submission: dict[str, LeaderboardEvidenceVerificationRef] = {}
    for report_ref in index.reports:
        if report_ref.submission_path in refs_by_submission:
            raise LeaderboardValidationError(
                "duplicate evidence index report for submission "
                f"{report_ref.submission_path} at {selected_path}"
            )
        _validate_evidence_report_ref(report_ref, selected_path)
        refs_by_submission[report_ref.submission_path] = report_ref
    return refs_by_submission


def _validate_evidence_index_summary(
    index: LeaderboardEvidenceVerificationIndex,
    index_path: Path,
) -> None:
    github_actions = sum(
        1 for report_ref in index.reports if report_ref.trust_level == "github_actions"
    )
    maintainer_rerun = sum(
        1 for report_ref in index.reports if report_ref.trust_level == "maintainer_rerun"
    )
    artifact_attestations = sum(
        1 for report_ref in index.reports if report_ref.artifact_attestation_report_path
    )
    if index.summary.total_reports != len(index.reports):
        raise LeaderboardValidationError(
            "leaderboard evidence index total_reports mismatch at "
            f"{index_path}: expected {len(index.reports)}, got {index.summary.total_reports}"
        )
    if index.summary.github_actions != github_actions:
        raise LeaderboardValidationError(
            "leaderboard evidence index github_actions count mismatch at "
            f"{index_path}: expected {github_actions}, got {index.summary.github_actions}"
        )
    if index.summary.maintainer_rerun != maintainer_rerun:
        raise LeaderboardValidationError(
            "leaderboard evidence index maintainer_rerun count mismatch at "
            f"{index_path}: expected {maintainer_rerun}, got {index.summary.maintainer_rerun}"
        )
    if index.summary.artifact_attestations != artifact_attestations:
        raise LeaderboardValidationError(
            "leaderboard evidence index artifact_attestations count mismatch at "
            f"{index_path}: expected {artifact_attestations}, "
            f"got {index.summary.artifact_attestations}"
        )


def _validate_evidence_report_ref(
    report_ref: LeaderboardEvidenceVerificationRef,
    index_path: Path,
) -> None:
    _validate_artifact_attestation_evidence_report(report_ref, index_path)
    report_path = _resolve_evidence_report_path(report_ref.report_path, index_path)
    if report_ref.report_schema_version == LEADERBOARD_GITHUB_RUN_VERIFICATION_SCHEMA_VERSION:
        _validate_github_run_evidence_report(report_ref, report_path)
        return
    if report_ref.report_schema_version == LEADERBOARD_MAINTAINER_RERUN_SCHEMA_VERSION:
        _validate_maintainer_rerun_evidence_report(report_ref, report_path)
        return
    raise LeaderboardValidationError(
        f"unsupported evidence report schema {report_ref.report_schema_version} at {index_path}"
    )


def _validate_artifact_attestation_evidence_report(
    report_ref: LeaderboardEvidenceVerificationRef,
    index_path: Path,
) -> None:
    report_path_text = report_ref.artifact_attestation_report_path
    subject_sha256 = report_ref.artifact_attestation_subject_sha256
    repository = report_ref.artifact_attestation_github_repository
    github_sha = report_ref.artifact_attestation_github_sha
    if not report_path_text:
        if subject_sha256 or repository or github_sha:
            raise LeaderboardValidationError(
                "artifact attestation evidence metadata exists without a report path at "
                f"{index_path}"
            )
        return
    if not subject_sha256 or not repository or not github_sha:
        raise LeaderboardValidationError(
            "artifact attestation evidence report path requires subject hash, repository, "
            "and GitHub SHA at "
            f"{index_path}"
        )

    from anvil.attestations import (  # noqa: PLC0415
        LeaderboardArtifactAttestationVerification,
    )

    report_path = _resolve_evidence_report_path(report_path_text, index_path)
    try:
        report = LeaderboardArtifactAttestationVerification.model_validate_json(
            report_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise LeaderboardValidationError(
            f"invalid artifact attestation evidence report at {report_path}: {error}"
        ) from error
    expected_fields: dict[str, object] = {
        "submission_path": report_ref.submission_path,
        "trust_level": "github_actions",
        "github_run_url": report_ref.github_run_url,
        "subject_sha256": subject_sha256,
        "github_repository": repository,
        "github_sha": github_sha,
        "source_digest": github_sha,
    }
    for field_name, expected_value in expected_fields.items():
        actual_value = getattr(report, field_name)
        if actual_value != expected_value:
            raise LeaderboardValidationError(
                f"artifact attestation evidence report {field_name} mismatch at {report_path}: "
                f"expected {expected_value!r}, got {actual_value!r}"
            )


def _resolve_evidence_report_path(raw_path: str, index_path: Path) -> Path:
    report_path = Path(raw_path)
    if report_path.is_absolute():
        return report_path
    cwd_report_path = Path.cwd() / report_path
    if cwd_report_path.exists():
        return cwd_report_path
    return index_path.parent / report_path


def _validate_github_run_evidence_report(
    report_ref: LeaderboardEvidenceVerificationRef,
    report_path: Path,
) -> None:
    try:
        report = LeaderboardGithubRunVerification.model_validate_json(
            report_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise LeaderboardValidationError(
            f"invalid GitHub run evidence report at {report_path}: {error}"
        ) from error
    expected_fields: dict[str, object] = {
        "submission_path": report_ref.submission_path,
        "trust_level": report_ref.trust_level,
        "evidence_sha256": report_ref.evidence_sha256,
        "github_run_url": report_ref.github_run_url,
    }
    for field_name, expected_value in expected_fields.items():
        actual_value = getattr(report, field_name)
        if actual_value != expected_value:
            raise LeaderboardValidationError(
                f"GitHub run evidence report {field_name} mismatch at {report_path}: "
                f"expected {expected_value!r}, got {actual_value!r}"
            )


def _validate_maintainer_rerun_evidence_report(
    report_ref: LeaderboardEvidenceVerificationRef,
    report_path: Path,
) -> None:
    try:
        report = LeaderboardMaintainerRerun.model_validate_json(
            report_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise LeaderboardValidationError(
            f"invalid maintainer rerun evidence report at {report_path}: {error}"
        ) from error
    expected_fields: dict[str, object] = {
        "original_evidence_sha256": report_ref.evidence_sha256,
        "github_run_url": report_ref.github_run_url,
    }
    for field_name, expected_value in expected_fields.items():
        actual_value = getattr(report, field_name)
        if actual_value != expected_value:
            raise LeaderboardValidationError(
                f"maintainer rerun evidence report {field_name} mismatch at {report_path}: "
                f"expected {expected_value!r}, got {actual_value!r}"
            )


def _audit_rows_with_evidence_index(
    rows: list[LeaderboardAuditRow],
    evidence_refs: dict[str, LeaderboardEvidenceVerificationRef],
    *,
    require_artifact_attestation: bool,
) -> list[LeaderboardAuditRow]:
    seen_submission_paths = {row.submission_path for row in rows}
    updated_rows: list[LeaderboardAuditRow] = []
    for row in rows:
        if row.decision == "reject" or row.trust_level not in {
            "github_actions",
            "maintainer_rerun",
        }:
            updated_rows.append(row)
            continue
        report_ref = evidence_refs.get(row.submission_path)
        if report_ref is None:
            updated_rows.append(
                row.model_copy(
                    update={
                        "decision": "reject",
                        "reason": ("verified trust row is missing from leaderboard evidence index"),
                        "github_run_status": "failed",
                    }
                )
            )
            continue
        mismatch_reason = _audit_evidence_index_mismatch(row, report_ref)
        if mismatch_reason:
            updated_rows.append(
                row.model_copy(
                    update={
                        "decision": "reject",
                        "reason": mismatch_reason,
                        "github_run_status": "failed",
                    }
                )
            )
            continue
        attestation_mismatch_reason = _audit_artifact_attestation_mismatch(
            row,
            report_ref,
            require_artifact_attestation=require_artifact_attestation,
        )
        if attestation_mismatch_reason:
            updated_rows.append(
                row.model_copy(
                    update={
                        "decision": "reject",
                        "reason": attestation_mismatch_reason,
                        "github_run_status": "verified",
                        "artifact_attestation_status": "failed",
                        "artifact_attestation_report_path": (
                            report_ref.artifact_attestation_report_path
                        ),
                        "artifact_attestation_subject_sha256": (
                            report_ref.artifact_attestation_subject_sha256
                        ),
                    }
                )
            )
            continue
        artifact_attestation_status = (
            "verified" if report_ref.artifact_attestation_report_path else "not checked"
        )
        reason = (
            "maintainer rerun provenance checks passed with evidence index"
            if row.trust_level == "maintainer_rerun"
            else "submission provenance checks passed with evidence index"
        )
        updated_rows.append(
            row.model_copy(
                update={
                    "decision": "accept",
                    "reason": reason,
                    "github_run_status": "verified",
                    "artifact_attestation_status": artifact_attestation_status,
                    "artifact_attestation_report_path": (
                        report_ref.artifact_attestation_report_path
                    ),
                    "artifact_attestation_subject_sha256": (
                        report_ref.artifact_attestation_subject_sha256
                    ),
                }
            )
        )

    for submission_path, report_ref in evidence_refs.items():
        if submission_path not in seen_submission_paths:
            updated_rows.append(
                LeaderboardAuditRow(
                    submission_path=submission_path,
                    decision="reject",
                    reason="leaderboard evidence index references a missing submission",
                    trust_level=report_ref.trust_level,
                    evidence_sha256=report_ref.evidence_sha256,
                    artifact_status="not checked",
                    github_run_status="failed",
                    artifact_attestation_status=(
                        "failed" if require_artifact_attestation else "not checked"
                    ),
                )
            )
    return updated_rows


def _audit_evidence_index_mismatch(
    row: LeaderboardAuditRow,
    report_ref: LeaderboardEvidenceVerificationRef,
) -> str:
    if report_ref.trust_level != row.trust_level:
        return (
            "evidence index mismatch: expected trust level "
            f"{row.trust_level}, got {report_ref.trust_level}"
        )
    if report_ref.evidence_sha256 != row.evidence_sha256:
        return (
            "evidence index mismatch: expected evidence hash "
            f"{row.evidence_sha256}, got {report_ref.evidence_sha256}"
        )
    if (
        row.trust_level == "maintainer_rerun"
        and report_ref.github_run_url != row.maintainer_rerun_url
    ):
        return (
            "evidence index mismatch: expected maintainer rerun URL "
            f"{row.maintainer_rerun_url}, got {report_ref.github_run_url}"
        )
    return ""


def _audit_artifact_attestation_mismatch(
    row: LeaderboardAuditRow,
    report_ref: LeaderboardEvidenceVerificationRef,
    *,
    require_artifact_attestation: bool,
) -> str:
    report_path = report_ref.artifact_attestation_report_path
    subject_sha256 = report_ref.artifact_attestation_subject_sha256
    if not report_path:
        return (
            "required GitHub artifact attestation evidence is missing"
            if require_artifact_attestation and row.trust_level == "github_actions"
            else ""
        )
    submission_path = Path(row.submission_path)
    if not submission_path.is_file():
        return f"artifact attestation submission file is missing: {submission_path}"
    actual_sha256 = _sha256_file(submission_path)
    if subject_sha256 != actual_sha256:
        return (
            "artifact attestation subject hash mismatch: "
            f"expected {actual_sha256}, got {subject_sha256 or 'not provided'}"
        )
    submission = validate_leaderboard_submission(submission_path, verify_artifacts=False)
    expected_repository = submission.verification.github_repository
    if report_ref.artifact_attestation_github_repository != expected_repository:
        return (
            "artifact attestation repository mismatch: "
            f"expected {expected_repository}, "
            f"got {report_ref.artifact_attestation_github_repository or 'not provided'}"
        )
    expected_github_sha = submission.verification.github_sha
    return (
        (
            "artifact attestation GitHub SHA mismatch: "
            f"expected {expected_github_sha}, "
            f"got {report_ref.artifact_attestation_github_sha or 'not provided'}"
        )
        if report_ref.artifact_attestation_github_sha != expected_github_sha
        else ""
    )


def audit_leaderboard_submissions(
    submissions_dir: str | Path,
    *,
    verify_artifacts: bool = False,
    verify_github_run: bool = False,
    maintainer_reruns_dir: str | Path | None = None,
    evidence_index_path: str | Path | None = None,
    require_artifact_attestation: bool = False,
) -> LeaderboardAuditReport:
    selected_submissions_dir = Path(submissions_dir)
    if not selected_submissions_dir.exists():
        raise LeaderboardValidationError(
            f"submissions directory missing: {selected_submissions_dir}"
        )
    files = sorted(
        path
        for path in selected_submissions_dir.rglob("*.json")
        if path.is_file() and path.name != "leaderboard.json"
    )
    if not files:
        raise LeaderboardValidationError(
            f"no submission JSON files found in {selected_submissions_dir}"
        )

    rows: list[LeaderboardAuditRow] = []
    seen_evidence_hashes: dict[str, Path] = {}
    maintainer_reruns = _load_maintainer_rerun_attestations(maintainer_reruns_dir)
    evidence_refs = _load_verified_evidence_refs(evidence_index_path)
    used_maintainer_reruns: set[str] = set()
    for path in files:
        row = _audit_submission_file(
            path,
            verify_artifacts=verify_artifacts,
            verify_github_run=verify_github_run,
        )
        if row.decision != "reject" and row.evidence_sha256 in maintainer_reruns:
            attestation_path, attestation = maintainer_reruns[row.evidence_sha256]
            used_maintainer_reruns.add(row.evidence_sha256)
            row = _audit_row_with_maintainer_rerun(
                path=path,
                row=row,
                attestation=attestation,
                attestation_path=attestation_path,
                verify_github_run=verify_github_run,
            )
        if row.decision != "reject" and row.evidence_sha256:
            duplicate_path = seen_evidence_hashes.get(row.evidence_sha256)
            if duplicate_path is not None:
                row = row.model_copy(
                    update={
                        "decision": "reject",
                        "reason": (
                            "duplicate evidence hash: "
                            f"{path} and {duplicate_path} both use {row.evidence_sha256}"
                        ),
                    }
                )
            else:
                seen_evidence_hashes[row.evidence_sha256] = path
        rows.append(row)
    unused_reruns = sorted(set(maintainer_reruns) - used_maintainer_reruns)
    for evidence_hash in unused_reruns:
        attestation_path, _ = maintainer_reruns[evidence_hash]
        rows.append(
            LeaderboardAuditRow(
                submission_path=str(_display_path(attestation_path)),
                decision="reject",
                reason=(
                    "maintainer rerun original_evidence_sha256 has no matching submission "
                    f"evidence: {evidence_hash}"
                ),
                evidence_sha256=evidence_hash,
                artifact_status="not checked",
                github_run_status="not checked",
                maintainer_rerun_path=str(_display_path(attestation_path)),
            )
        )

    if require_artifact_attestation and evidence_index_path is None:
        raise LeaderboardValidationError("--require-artifact-attestation requires --evidence-index")
    if evidence_refs:
        rows = _audit_rows_with_evidence_index(
            rows,
            evidence_refs,
            require_artifact_attestation=require_artifact_attestation,
        )

    summary = LeaderboardAuditSummary(
        total=len(rows),
        accept=sum(1 for row in rows if row.decision == "accept"),
        review=sum(1 for row in rows if row.decision == "review"),
        reject=sum(1 for row in rows if row.decision == "reject"),
    )
    markdown = _leaderboard_audit_markdown(
        submissions_dir=selected_submissions_dir,
        evidence_index_path=Path(evidence_index_path) if evidence_index_path is not None else None,
        summary=summary,
        rows=rows,
    )
    return LeaderboardAuditReport(
        schema_version=LEADERBOARD_AUDIT_SCHEMA_VERSION,
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        generated_by=f"agent-anvil/{_anvil_version()}",
        submissions_dir=str(_display_path(selected_submissions_dir)),
        evidence_index_path=(
            str(_display_path(Path(evidence_index_path))) if evidence_index_path is not None else ""
        ),
        require_artifact_attestation=require_artifact_attestation,
        summary=summary,
        rows=rows,
        markdown=markdown,
    )


def _verify_artifact_attestation(
    submission_path: Path,
) -> LeaderboardArtifactAttestationVerification:
    from anvil.attestations import (  # noqa: PLC0415
        verify_leaderboard_artifact_attestation,
    )

    return verify_leaderboard_artifact_attestation(submission_path)


def _audit_submission_file(
    path: Path,
    *,
    verify_artifacts: bool,
    verify_github_run: bool,
) -> LeaderboardAuditRow:
    artifact_status: Literal["verified", "not checked", "failed"] = (
        "not checked" if not verify_artifacts else "verified"
    )
    github_run_status: Literal["verified", "not checked", "failed"] = "not checked"
    try:
        submission = validate_leaderboard_submission(
            path,
            verify_artifacts=verify_artifacts,
            verify_github_run=False,
        )
        if verify_github_run and submission.verification.trust_level == "github_actions":
            try:
                _validate_github_actions_run(submission)
                github_run_status = "verified"
            except LeaderboardValidationError as error:
                return _audit_row_from_submission(
                    path=path,
                    submission=submission,
                    decision="reject",
                    reason=f"GitHub run verification failed: {error}",
                    artifact_status=artifact_status,
                    github_run_status="failed",
                )
    except LeaderboardValidationError as error:
        return LeaderboardAuditRow(
            submission_path=str(_display_path(path)),
            decision="reject",
            reason=str(error),
            artifact_status="failed" if verify_artifacts else "not checked",
            github_run_status="not checked",
        )

    trust_level = submission.verification.trust_level
    if trust_level == "self_reported":
        return _audit_row_from_submission(
            path=path,
            submission=submission,
            decision="review",
            reason="self-reported rows require human review",
            artifact_status=artifact_status,
            github_run_status=github_run_status,
        )
    if trust_level == "github_actions" and not verify_github_run:
        return _audit_row_from_submission(
            path=path,
            submission=submission,
            decision="review",
            reason="github_actions rows require --github-run verification",
            artifact_status=artifact_status,
            github_run_status=github_run_status,
        )
    if trust_level == "github_actions" and github_run_status != "verified":
        return _audit_row_from_submission(
            path=path,
            submission=submission,
            decision="review",
            reason="github_actions rows should include verified GitHub run evidence",
            artifact_status=artifact_status,
            github_run_status=github_run_status,
        )
    return _audit_row_from_submission(
        path=path,
        submission=submission,
        decision="accept",
        reason="submission provenance checks passed",
        artifact_status=artifact_status,
        github_run_status=github_run_status,
    )


def _audit_row_with_maintainer_rerun(
    *,
    path: Path,
    row: LeaderboardAuditRow,
    attestation: LeaderboardMaintainerRerun,
    attestation_path: Path,
    verify_github_run: bool,
) -> LeaderboardAuditRow:
    try:
        submission = validate_leaderboard_submission(
            path,
            verify_artifacts=False,
            verify_github_run=False,
        )
        _validate_maintainer_rerun_attestation(
            attestation,
            submission,
            attestation_path=attestation_path,
            verify_github_run=verify_github_run,
        )
    except LeaderboardValidationError as error:
        return row.model_copy(
            update={
                "decision": "reject",
                "reason": f"maintainer rerun verification failed: {error}",
                "trust_level": "maintainer_rerun",
                "github_run_status": "failed" if verify_github_run else row.github_run_status,
                "maintainer_rerun_path": str(_display_path(attestation_path)),
                "maintainer_rerun_url": attestation.github_run_url,
                "maintainer_rerun_evidence_sha256": attestation.rerun_evidence_sha256,
            }
        )
    decision: Literal["accept", "review"] = "accept" if verify_github_run else "review"
    reason = (
        "maintainer rerun provenance checks passed"
        if verify_github_run
        else "maintainer_rerun rows require --github-run verification"
    )
    github_run_status: Literal["verified", "not checked", "failed"] = (
        "verified" if verify_github_run else "not checked"
    )
    return row.model_copy(
        update={
            "decision": decision,
            "reason": reason,
            "trust_level": "maintainer_rerun",
            "github_run_status": github_run_status,
            "maintainer_rerun_path": str(_display_path(attestation_path)),
            "maintainer_rerun_url": attestation.github_run_url,
            "maintainer_rerun_evidence_sha256": attestation.rerun_evidence_sha256,
        }
    )


def _audit_row_from_submission(
    *,
    path: Path,
    submission: LeaderboardSubmission,
    decision: Literal["accept", "review", "reject"],
    reason: str,
    artifact_status: Literal["verified", "not checked", "failed"],
    github_run_status: Literal["verified", "not checked", "failed"],
) -> LeaderboardAuditRow:
    return LeaderboardAuditRow(
        submission_path=str(_display_path(path)),
        decision=decision,
        reason=reason,
        agent_name=submission.submitter.agent_name,
        benchmark_name=submission.benchmark.name,
        trust_level=submission.verification.trust_level,
        trace_aware_pass_rate=submission.metrics.trace_aware_pass_rate,
        evidence_sha256=submission.verification.evidence_sha256,
        artifact_status=artifact_status,
        github_run_status=github_run_status,
    )


def _leaderboard_audit_markdown(
    *,
    submissions_dir: Path,
    evidence_index_path: Path | None,
    summary: LeaderboardAuditSummary,
    rows: list[LeaderboardAuditRow],
) -> str:
    lines = [
        "# Agent Anvil Leaderboard Audit",
        "",
        "## Summary",
        "",
        f"- Submissions: `{_display_path(submissions_dir)}`",
    ]
    if evidence_index_path is not None:
        lines.append(f"- Evidence index: `{_display_path(evidence_index_path)}`")
    lines.extend(
        [
            f"- Total: {summary.total}",
            f"- Accept: {summary.accept}",
            f"- Review: {summary.review}",
            f"- Reject: {summary.reject}",
            "",
            "## Decisions",
            "",
            "| Decision | Submission | Agent | Trust | Reason |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    lines.extend(
        (
            "| "
            f"{row.decision} | "
            f"`{row.submission_path}` | "
            f"{row.agent_name or 'unknown'} | "
            f"{row.trust_level or 'unknown'} | "
            f"{row.reason} |"
        )
        for row in rows
    )
    lines.append("")
    return "\n".join(lines)


def _github_run_verification_report(
    selected_submission_path: Path,
    submission: LeaderboardSubmission,
) -> LeaderboardGithubRunVerification:
    verification = submission.verification
    return LeaderboardGithubRunVerification(
        schema_version=LEADERBOARD_GITHUB_RUN_VERIFICATION_SCHEMA_VERSION,
        status="verified",
        submission_path=str(_display_path(selected_submission_path)),
        agent_name=submission.submitter.agent_name,
        benchmark_name=submission.benchmark.name,
        trust_level="github_actions",
        github_repository=verification.github_repository,
        github_sha=verification.github_sha,
        github_run_url=verification.github_run_url,
        evidence_sha256=verification.evidence_sha256,
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        generated_by=f"agent-anvil/{_anvil_version()}",
    )


def create_maintainer_rerun_attestation(
    *,
    original_submission_path: str | Path,
    rerun_submission_path: str | Path,
    out_path: str | Path,
    github_run_url: str,
    github_repository: str = "",
    github_sha: str = "",
    notes: str = "",
) -> LeaderboardMaintainerRerun:
    selected_original_path = Path(original_submission_path)
    selected_rerun_path = Path(rerun_submission_path)
    selected_out_path = Path(out_path)
    original = validate_leaderboard_submission(
        selected_original_path,
        verify_artifacts=False,
    )
    rerun = validate_leaderboard_submission(
        selected_rerun_path,
        verify_artifacts=False,
    )
    _validate_rerun_submission_matches_original(
        original=original,
        rerun=rerun,
        rerun_path=selected_rerun_path,
    )
    attestation = LeaderboardMaintainerRerun(
        schema_version=LEADERBOARD_MAINTAINER_RERUN_SCHEMA_VERSION,
        status="verified",
        original_evidence_sha256=original.verification.evidence_sha256,
        rerun_evidence_sha256=rerun.verification.evidence_sha256,
        agent_name=original.submitter.agent_name,
        benchmark_name=original.benchmark.name,
        total_trials=original.metrics.total_trials,
        final_answer_pass_rate=original.metrics.final_answer_pass_rate,
        trace_aware_pass_rate=original.metrics.trace_aware_pass_rate,
        github_run_url=github_run_url,
        github_repository=github_repository,
        github_sha=github_sha,
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        generated_by=f"agent-anvil/{_anvil_version()}",
        notes=notes,
    )
    _validate_maintainer_rerun_attestation(
        attestation,
        original,
        attestation_path=selected_out_path,
    )
    selected_out_path.parent.mkdir(parents=True, exist_ok=True)
    selected_out_path.write_text(attestation.model_dump_json(indent=2), encoding="utf-8")
    return attestation


def validate_maintainer_rerun_attestation(
    *,
    original_submission_path: str | Path,
    attestation_path: str | Path,
    verify_github_run: bool = False,
) -> LeaderboardMaintainerRerun:
    selected_original_path = Path(original_submission_path)
    selected_attestation_path = Path(attestation_path)
    original = validate_leaderboard_submission(
        selected_original_path,
        verify_artifacts=False,
    )
    try:
        attestation = LeaderboardMaintainerRerun.model_validate_json(
            selected_attestation_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise LeaderboardValidationError(
            f"invalid maintainer rerun attestation at {selected_attestation_path}: {error}"
        ) from error
    _validate_maintainer_rerun_attestation(
        attestation,
        original,
        attestation_path=selected_attestation_path,
        verify_github_run=verify_github_run,
    )
    return attestation


def _validate_rerun_submission_matches_original(
    *,
    original: LeaderboardSubmission,
    rerun: LeaderboardSubmission,
    rerun_path: Path,
) -> None:
    expected_fields: dict[str, object] = {
        "agent_name": original.submitter.agent_name,
        "benchmark_name": original.benchmark.name,
        "total_trials": original.metrics.total_trials,
        "final_answer_pass_rate": original.metrics.final_answer_pass_rate,
        "trace_aware_pass_rate": original.metrics.trace_aware_pass_rate,
    }
    actual_fields: dict[str, object] = {
        "agent_name": rerun.submitter.agent_name,
        "benchmark_name": rerun.benchmark.name,
        "total_trials": rerun.metrics.total_trials,
        "final_answer_pass_rate": rerun.metrics.final_answer_pass_rate,
        "trace_aware_pass_rate": rerun.metrics.trace_aware_pass_rate,
    }
    for field_name, expected_value in expected_fields.items():
        actual_value = actual_fields[field_name]
        if actual_value != expected_value:
            raise LeaderboardValidationError(
                f"maintainer rerun {field_name} mismatch in {rerun_path}: "
                f"expected {expected_value!r}, got {actual_value!r}"
            )


def _load_maintainer_rerun_attestations(
    maintainer_reruns_dir: str | Path | None,
) -> dict[str, tuple[Path, LeaderboardMaintainerRerun]]:
    if maintainer_reruns_dir is None:
        return {}
    selected_dir = Path(maintainer_reruns_dir)
    if not selected_dir.exists():
        raise LeaderboardValidationError(f"maintainer reruns directory missing: {selected_dir}")
    files = sorted(path for path in selected_dir.rglob("*.json") if path.is_file())
    attestations: dict[str, tuple[Path, LeaderboardMaintainerRerun]] = {}
    for path in files:
        try:
            attestation = LeaderboardMaintainerRerun.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as error:
            raise LeaderboardValidationError(
                f"invalid maintainer rerun attestation at {path}: {error}"
            ) from error
        evidence_hash = attestation.original_evidence_sha256
        if evidence_hash in attestations:
            previous_path, _ = attestations[evidence_hash]
            raise LeaderboardValidationError(
                "duplicate maintainer rerun attestation for evidence hash "
                f"{evidence_hash}: {path} and {previous_path}"
            )
        attestations[evidence_hash] = (path, attestation)
    return attestations


def _validate_maintainer_rerun_attestation(
    attestation: LeaderboardMaintainerRerun,
    submission: LeaderboardSubmission,
    *,
    attestation_path: Path,
    verify_github_run: bool = False,
) -> None:
    expected_hash = submission.verification.evidence_sha256
    if attestation.original_evidence_sha256 != expected_hash:
        raise LeaderboardValidationError(
            f"maintainer rerun original_evidence_sha256 mismatch at {attestation_path}: "
            f"expected {expected_hash}, got {attestation.original_evidence_sha256}"
        )
    expected_fields: dict[str, object] = {
        "agent_name": submission.submitter.agent_name,
        "benchmark_name": submission.benchmark.name,
        "total_trials": submission.metrics.total_trials,
        "final_answer_pass_rate": submission.metrics.final_answer_pass_rate,
        "trace_aware_pass_rate": submission.metrics.trace_aware_pass_rate,
    }
    for field_name, expected_value in expected_fields.items():
        actual_value = getattr(attestation, field_name)
        if actual_value != expected_value:
            raise LeaderboardValidationError(
                f"maintainer rerun {field_name} mismatch at {attestation_path}: "
                f"expected {expected_value!r}, got {actual_value!r}"
            )
    _validate_maintainer_rerun_run_url(attestation.github_run_url, attestation_path)
    if verify_github_run:
        _validate_maintainer_rerun_github_run(attestation, attestation_path)


def _validate_maintainer_rerun_run_url(run_url: str, attestation_path: Path) -> None:
    _maintainer_rerun_run_reference(run_url, "", attestation_path)


def _validate_maintainer_rerun_github_run(
    attestation: LeaderboardMaintainerRerun,
    attestation_path: Path,
) -> None:
    repository, run_id, host = _maintainer_rerun_run_reference(
        attestation.github_run_url,
        attestation.github_repository,
        attestation_path,
    )
    payload = _fetch_github_actions_run(
        repository,
        run_id,
        token=_github_api_token(),
        host=host,
    )
    run_repository = _github_run_repository(payload)
    if run_repository != repository:
        raise LeaderboardValidationError(
            "maintainer rerun GitHub Actions run repository mismatch: "
            f"expected {repository}, got {run_repository or 'not provided'}"
        )

    head_sha = str(payload.get("head_sha") or "")
    if attestation.github_sha and head_sha != attestation.github_sha:
        raise LeaderboardValidationError(
            "maintainer rerun GitHub Actions run head_sha mismatch: "
            f"expected {attestation.github_sha}, got {head_sha or 'not provided'}"
        )

    status = str(payload.get("status") or "")
    if status != "completed":
        raise LeaderboardValidationError(
            "maintainer rerun GitHub Actions run status mismatch: expected completed, "
            f"got {status or 'not provided'}"
        )

    conclusion = str(payload.get("conclusion") or "")
    if conclusion != "success":
        raise LeaderboardValidationError(
            "maintainer rerun GitHub Actions run conclusion mismatch: expected success, "
            f"got {conclusion or 'not provided'}"
        )


def _maintainer_rerun_run_reference(
    run_url: str,
    expected_repository: str,
    attestation_path: Path,
) -> tuple[str, str, str]:
    parsed = urlparse(run_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise LeaderboardValidationError(
            f"maintainer rerun github_run_url must be an absolute HTTPS URL at {attestation_path}"
        )
    path_parts = [part for part in parsed.path.strip("/").split("/") if part]
    min_run_path_parts = 5
    if len(path_parts) < min_run_path_parts or path_parts[2:4] != ["actions", "runs"]:
        raise LeaderboardValidationError(
            "maintainer rerun github_run_url must look like "
            f"https://github.com/OWNER/REPO/actions/runs/RUN_ID at {attestation_path}"
        )
    repository = f"{path_parts[0]}/{path_parts[1]}"
    if expected_repository and repository != expected_repository:
        raise LeaderboardValidationError(
            "maintainer rerun github_run_url repository mismatch: "
            f"expected {expected_repository}, got {repository}"
        )
    run_id = path_parts[4]
    return expected_repository or repository, run_id, parsed.hostname


def _validate_required_row_trust_level(
    rows: list[LeaderboardRow],
    require_trust_level: str,
) -> None:
    for row in rows:
        if row.trust_level != require_trust_level:
            raise LeaderboardValidationError(
                f"trust level mismatch: expected {require_trust_level}, got {row.trust_level}"
            )


def build_leaderboard_index(
    submissions_dir: str | Path,
    *,
    csv_path: str | Path | None = None,
    json_path: str | Path | None = None,
    verify_artifacts: bool = False,
    require_trust_level: str | None = None,
    verify_github_run: bool = False,
    maintainer_reruns_dir: str | Path | None = None,
) -> LeaderboardIndex:
    selected_submissions_dir = Path(submissions_dir)
    submissions = _load_submission_files(
        selected_submissions_dir,
        verify_artifacts=verify_artifacts,
        require_trust_level=None,
        verify_github_run=verify_github_run,
    )
    maintainer_reruns = _load_maintainer_rerun_attestations(maintainer_reruns_dir)
    rows: list[LeaderboardRow] = []
    used_maintainer_reruns: set[str] = set()
    for submission_path, submission in submissions:
        row = _row_from_submission(submission_path, submission)
        evidence_hash = submission.verification.evidence_sha256
        if evidence_hash in maintainer_reruns:
            attestation_path, attestation = maintainer_reruns[evidence_hash]
            _validate_maintainer_rerun_attestation(
                attestation,
                submission,
                attestation_path=attestation_path,
                verify_github_run=verify_github_run,
            )
            used_maintainer_reruns.add(evidence_hash)
            row = row.model_copy(
                update={
                    "trust_level": "maintainer_rerun",
                    "github_run_url": attestation.github_run_url,
                    "maintainer_rerun_url": attestation.github_run_url,
                    "maintainer_rerun_path": str(_display_path(attestation_path)),
                    "maintainer_rerun_evidence_sha256": attestation.rerun_evidence_sha256,
                    "maintainer_rerun_github_repository": attestation.github_repository,
                    "maintainer_rerun_github_sha": attestation.github_sha,
                    "maintainer_rerun_generated_at": attestation.generated_at,
                    "maintainer_rerun_generated_by": attestation.generated_by,
                }
            )
        rows.append(row)
    unused_reruns = sorted(set(maintainer_reruns) - used_maintainer_reruns)
    if unused_reruns:
        raise LeaderboardValidationError(
            "maintainer rerun original_evidence_sha256 has no matching submission evidence: "
            + ", ".join(unused_reruns)
        )
    if require_trust_level:
        _validate_required_row_trust_level(rows, require_trust_level)
    rows = _rank_rows(rows)
    index = LeaderboardIndex(
        schema_version=LEADERBOARD_INDEX_SCHEMA_VERSION,
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        generated_by=f"agent-anvil/{_anvil_version()}",
        rows=rows,
    )
    if csv_path is not None:
        _write_leaderboard_csv(index, Path(csv_path))
    if json_path is not None:
        selected_json_path = Path(json_path)
        selected_json_path.parent.mkdir(parents=True, exist_ok=True)
        selected_json_path.write_text(index.model_dump_json(indent=2), encoding="utf-8")
    return index


def prepare_leaderboard_pr_submission(
    *,
    submission_path: str | Path,
    leaderboard_repo: str | Path,
    submission_name: str | None = None,
    pr_body_out: str | Path | None = None,
    force: bool = False,
    require_trust_level: str | None = None,
    verify_github_run: bool = False,
) -> LeaderboardPrPreparation:
    selected_submission_path = Path(submission_path)
    selected_leaderboard_repo = Path(leaderboard_repo)
    submission = validate_leaderboard_submission(
        selected_submission_path,
        verify_artifacts=False,
        require_trust_level=require_trust_level,
        verify_github_run=verify_github_run,
    )
    submissions_dir = selected_leaderboard_repo / "submissions"
    submissions_dir.mkdir(parents=True, exist_ok=True)
    filename = _submission_filename(submission, submission_name=submission_name)
    target_path = submissions_dir / filename
    if target_path.exists() and not force:
        raise LeaderboardValidationError(
            f"{target_path} already exists. Re-run with --force to overwrite it."
        )
    shutil.copyfile(selected_submission_path, target_path)
    branch_name = f"add-{target_path.stem}-submission"
    commit_message = f"Add {target_path.stem} leaderboard submission"
    pr_title = f"Add {submission.submitter.agent_name} leaderboard submission"
    pr_body = _leaderboard_pr_body(
        submission=submission,
        target_path=target_path,
        leaderboard_repo=selected_leaderboard_repo,
    )
    if pr_body_out is not None:
        selected_pr_body_out = Path(pr_body_out)
        selected_pr_body_out.parent.mkdir(parents=True, exist_ok=True)
        selected_pr_body_out.write_text(pr_body, encoding="utf-8")
    return LeaderboardPrPreparation(
        submission=submission,
        target_path=target_path,
        branch_name=branch_name,
        commit_message=commit_message,
        pr_title=pr_title,
        pr_body=pr_body,
        next_steps=_leaderboard_pr_next_steps(
            target_path=target_path,
            leaderboard_repo=selected_leaderboard_repo,
            branch_name=branch_name,
            commit_message=commit_message,
            pr_title=pr_title,
            pr_body_path=Path(pr_body_out) if pr_body_out is not None else None,
        ),
    )


def _inspection_warnings(
    submission: LeaderboardSubmission,
    artifact_status: str,
    artifact_error: str,
    github_run_status: str,
    github_run_error: str,
) -> list[str]:
    warnings: list[str] = []
    trust_level = submission.verification.trust_level
    if trust_level == "self_reported":
        warnings.append("self-reported; prefer a github_actions or maintainer_rerun row")
    if trust_level == "github_actions" and not submission.verification.github_run_url:
        warnings.append("github_actions row is missing verification.github_run_url")
    if not submission.submitter.repo_url:
        warnings.append("submitter.repo_url is empty; reproduction requires a public source repo")
    if not submission.submitter.commit_sha:
        warnings.append("submitter.commit_sha is empty; reproduction requires a fixed commit")
    if artifact_status == "failed" and artifact_error:
        warnings.append(f"artifact verification failed: {artifact_error}")
    if github_run_status == "failed" and github_run_error:
        warnings.append(f"GitHub run verification failed: {github_run_error}")
    return warnings


def _inspection_markdown(
    *,
    submission: LeaderboardSubmission,
    artifact_status: str,
    artifact_error: str,
    github_run_status: str,
    github_run_error: str,
    warnings: tuple[str, ...],
) -> str:
    submitter = submission.submitter
    version = f" ({submitter.agent_version})" if submitter.agent_version else ""
    lines = [
        "# Agent Anvil Leaderboard Inspection",
        "",
        "## Summary",
        "",
        f"- Agent: {submitter.agent_name}{version}",
        f"- Repository: {submitter.repo_url or 'not provided'}",
        f"- Commit: {submitter.commit_sha or 'not provided'}",
        f"- Benchmark: {submission.benchmark.name}",
        f"- Benchmark scenarios: {len(submission.benchmark.scenario_hashes)}",
        f"- Total trials: {submission.metrics.total_trials}",
        f"- Trace-aware pass rate: {submission.metrics.trace_aware_pass_rate:.1f}%",
        f"- Final-answer pass rate: {submission.metrics.final_answer_pass_rate:.1f}%",
        f"- Answer-only missed failures: {submission.metrics.answer_only_missed_failures}",
        "",
        "## Trust Evidence",
        "",
        f"- Trust level: {submission.verification.trust_level}",
        f"- Evidence SHA-256: {submission.verification.evidence_sha256}",
        f"- Generated by: {submission.verification.generated_by}",
        f"- Generated at: {submission.verification.generated_at}",
        f"- GitHub run: {submission.verification.github_run_url or 'not provided'}",
        f"- GitHub repository: {submission.verification.github_repository or 'not provided'}",
        f"- GitHub SHA: {submission.verification.github_sha or 'not provided'}",
        f"- GitHub run verification: {github_run_status}",
        f"- Artifact hashes: {artifact_status}",
    ]
    if github_run_error:
        lines.append(f"- GitHub run error: {github_run_error}")
    if artifact_error:
        lines.append(f"- Artifact error: {artifact_error}")

    lines.extend(
        [
            "",
            "## Benchmark Hashes",
            "",
            f"- Manifest: `{submission.benchmark.manifest_path}`",
            f"- Manifest SHA-256: `{submission.benchmark.manifest_sha256}`",
        ]
    )
    for scenario_path, scenario_hash in submission.benchmark.scenario_hashes.items():
        lines.append(f"- Scenario: `{scenario_path}` -> `{scenario_hash}`")

    lines.extend(["", "## Reproducibility Checklist", ""])
    lines.extend(_reproducibility_steps(submission))

    lines.extend(["", "## Review Warnings", ""])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def _reproducibility_steps(submission: LeaderboardSubmission) -> list[str]:
    lines: list[str] = []
    repo_url = submission.submitter.repo_url
    commit_sha = submission.submitter.commit_sha
    if repo_url and commit_sha:
        repo_dir = _repo_dir_name(repo_url)
        lines.extend(
            [
                "1. Check out the submitted source revision:",
                "",
                "```bash",
                f"git clone {repo_url}",
                f"cd {repo_dir}",
                f"git checkout {commit_sha}",
                "```",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "1. Ask the submitter for a public repository URL and commit SHA.",
                "",
            ]
        )

    export_parts = [
        "uv run anvil leaderboard export",
        submission.artifacts.results_json_path,
        "--manifest",
        submission.benchmark.manifest_path,
        "--out",
        "leaderboard_submission.json",
        "--agent-name",
        _shell_quote(submission.submitter.agent_name),
    ]
    if submission.submitter.agent_version:
        export_parts.extend(["--agent-version", _shell_quote(submission.submitter.agent_version)])
    if repo_url:
        export_parts.extend(["--repo-url", _shell_quote(repo_url)])
    if commit_sha:
        export_parts.extend(["--commit-sha", _shell_quote(commit_sha)])

    lines.extend(
        [
            "2. Re-run the benchmark and export a comparable submission:",
            "",
            "```bash",
            f"uv run anvil paper reproduce --manifest {submission.benchmark.manifest_path}",
            " ".join(export_parts),
            "uv run anvil leaderboard validate leaderboard_submission.json",
            "```",
        ]
    )
    return lines


def _reproduction_script(
    *,
    submission: LeaderboardSubmission,
    submission_path: Path,
) -> str:
    runner = _anvil_runner(submission.verification.generated_by)
    repo_url = submission.submitter.repo_url
    commit_sha = submission.submitter.commit_sha
    agent_version_args = []
    if submission.submitter.agent_version:
        agent_version_args = [
            "--agent-version",
            _shell_quote(submission.submitter.agent_version),
        ]

    export_parts = [
        runner,
        "anvil leaderboard export",
        _shell_quote(submission.artifacts.results_json_path),
        "--manifest",
        _shell_quote(submission.benchmark.manifest_path),
        "--out",
        "reproduced_submission.json",
        "--agent-name",
        _shell_quote(submission.submitter.agent_name),
        *agent_version_args,
        "--repo-url",
        _shell_quote(repo_url),
        "--commit-sha",
        _shell_quote(commit_sha),
    ]

    original_submission = _shell_quote(str(submission_path))
    manifest_arg = _shell_quote(submission.benchmark.manifest_path)
    paper_command = f"{runner} anvil paper reproduce --manifest {manifest_arg}"
    validate_command = f"{runner} anvil leaderboard validate reproduced_submission.json"
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            "# Generated by Agent Anvil. Review this script before executing it.",
            "# It checks whether a submitted leaderboard row can be reproduced from",
            "# the claimed repository, commit, benchmark manifest, and result artifact.",
            "",
            'WORKDIR="${ANVIL_REPRO_WORKDIR:-agent-anvil-reproduction}"',
            'if [ -e "$WORKDIR" ]; then',
            '  echo "Refusing to overwrite existing $WORKDIR" >&2',
            "  exit 1",
            "fi",
            'mkdir -p "$WORKDIR"',
            f'cp {original_submission} "$WORKDIR/original_submission.json"',
            'cd "$WORKDIR"',
            f"git clone {_shell_quote(repo_url)} source",
            "cd source",
            f"git checkout {_shell_quote(commit_sha)}",
            "",
            paper_command,
            " ".join(export_parts),
            f"{validate_command} --no-artifacts",
            "",
            "python - <<'PY'",
            "import json",
            "from pathlib import Path",
            "",
            "original = json.loads(Path('../original_submission.json').read_text())",
            "reproduced = json.loads(Path('reproduced_submission.json').read_text())",
            "pairs = [",
            "    ('verification', 'evidence_sha256'),",
            "    ('metrics', 'trace_aware_pass_rate'),",
            "    ('metrics', 'final_answer_pass_rate'),",
            "    ('metrics', 'answer_only_missed_failures'),",
            "]",
            "mismatches = []",
            "for section, field in pairs:",
            "    name = f'{section}.{field}'",
            "    expected = original[section][field]",
            "    actual = reproduced[section][field]",
            "    if expected != actual:",
            "        mismatches.append(f'{name}: expected {expected!r}, got {actual!r}')",
            "if mismatches:",
            "    message = 'leaderboard reproduction mismatch:\\n' + '\\n'.join(mismatches)",
            "    raise SystemExit(message)",
            "print('reproduction check passed: evidence hash and headline metrics match')",
            "PY",
            "",
        ]
    )


def _anvil_runner(generated_by: str) -> str:
    prefix = "agent-anvil/"
    if generated_by.startswith(prefix):
        version_text = generated_by[len(prefix) :]
        if re.fullmatch(r"\d+\.\d+\.\d+(?:[a-zA-Z0-9._-]*)?", version_text):
            return f"uvx --from git+https://github.com/agent-axiom/agent-anvil@v{version_text}"
    return "uv run"


def _repo_dir_name(repo_url: str) -> str:
    name = repo_url.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or "repo"


def _shell_quote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:@%+=,-]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _load_submission_files(
    submissions_dir: Path,
    *,
    verify_artifacts: bool,
    require_trust_level: str | None,
    verify_github_run: bool,
) -> list[tuple[Path, LeaderboardSubmission]]:
    if not submissions_dir.exists():
        raise LeaderboardValidationError(f"submissions directory missing: {submissions_dir}")
    files = sorted(
        path
        for path in submissions_dir.rglob("*.json")
        if path.is_file() and path.name != "leaderboard.json"
    )
    if not files:
        raise LeaderboardValidationError(f"no submission JSON files found in {submissions_dir}")

    submissions: list[tuple[Path, LeaderboardSubmission]] = []
    seen_evidence_hashes: dict[str, Path] = {}
    for path in files:
        submission = validate_leaderboard_submission(
            path,
            verify_artifacts=verify_artifacts,
            require_trust_level=require_trust_level,
            verify_github_run=verify_github_run,
        )
        evidence_hash = submission.verification.evidence_sha256
        if evidence_hash in seen_evidence_hashes:
            raise LeaderboardValidationError(
                "duplicate evidence hash: "
                f"{path} and {seen_evidence_hashes[evidence_hash]} both use {evidence_hash}"
            )
        seen_evidence_hashes[evidence_hash] = path
        submissions.append((path, submission))
    return submissions


def _submission_filename(
    submission: LeaderboardSubmission,
    *,
    submission_name: str | None,
) -> str:
    if submission_name:
        name = Path(submission_name).name
        if name != submission_name:
            raise LeaderboardValidationError("--submission-name must be a file name, not a path")
        return name if name.endswith(".json") else f"{name}.json"
    return f"{_slug(submission.submitter.agent_name)}.json"


def _leaderboard_pr_next_steps(
    *,
    target_path: Path,
    leaderboard_repo: Path,
    branch_name: str,
    commit_message: str,
    pr_title: str,
    pr_body_path: Path | None,
) -> str:
    display_target = target_path.relative_to(leaderboard_repo)
    create_parts = [
        "gh pr create",
        "--repo agent-axiom/agent-anvil-leaderboard",
        "--head",
        branch_name,
        "--title",
        _shell_quote(pr_title),
    ]
    if pr_body_path is not None:
        create_parts.extend(["--body-file", _shell_quote(str(pr_body_path))])
    else:
        create_parts.append("--fill")
    return "\n".join(
        [
            f"cd {leaderboard_repo}",
            f"git checkout -b {branch_name}",
            f"git add {display_target}",
            f"git commit -m {_shell_quote(commit_message)}",
            f"git push --set-upstream origin {branch_name}",
            " ".join(create_parts),
        ]
    )


def _leaderboard_pr_body(
    *,
    submission: LeaderboardSubmission,
    target_path: Path,
    leaderboard_repo: Path,
) -> str:
    display_target = target_path.relative_to(leaderboard_repo)
    verification = submission.verification
    lines = [
        "## Agent Anvil leaderboard submission",
        "",
        "### Summary",
        "",
        f"- Agent: {submission.submitter.agent_name}",
        f"- Agent version: {submission.submitter.agent_version or 'not provided'}",
        f"- Benchmark: {submission.benchmark.name}",
        f"- Total trials: {submission.metrics.total_trials}",
        f"- Trace-aware pass rate: {submission.metrics.trace_aware_pass_rate:.1f}%",
        f"- Final-answer pass rate: {submission.metrics.final_answer_pass_rate:.1f}%",
        f"- Answer-only missed failures: {submission.metrics.answer_only_missed_failures}",
        f"- Trust level: {verification.trust_level}",
        f"- Evidence SHA-256: {verification.evidence_sha256}",
        f"- GitHub run: {verification.github_run_url or 'not provided'}",
        "",
        "### Submitted file",
        "",
        f"`{display_target}`",
        "",
        "### Reviewer checks",
        "",
        "```bash",
        f"uv run anvil leaderboard validate {display_target} --no-artifacts",
        f"uv run anvil leaderboard inspect {display_target} --no-artifacts",
        "```",
    ]
    if verification.trust_level == "github_actions" and verification.github_repository:
        lines.extend(
            [
                "",
                "Verify the GitHub artifact attestation for the submitted JSON bytes:",
                "",
                "```bash",
                f"gh attestation verify {display_target} -R {verification.github_repository}",
                "```",
            ]
        )
    lines.extend(
        [
            "",
            "### Trust boundary",
            "",
            "The leaderboard repository validates aggregate metadata and provenance, but it "
            "does not execute arbitrary user code. Maintainers can run `anvil leaderboard "
            "reproduce` in a sandbox if independent rerun evidence is needed.",
            "",
        ]
    )
    return "\n".join(lines)


def _row_from_submission(
    submission_path: Path,
    submission: LeaderboardSubmission,
) -> LeaderboardRow:
    return LeaderboardRow(
        rank=0,
        submission_path=str(_display_path(submission_path)),
        submission_schema_version=submission.schema_version,
        submission_generated_by=submission.verification.generated_by,
        agent_name=submission.submitter.agent_name,
        agent_version=submission.submitter.agent_version,
        repo_url=submission.submitter.repo_url,
        commit_sha=submission.submitter.commit_sha,
        benchmark_name=submission.benchmark.name,
        benchmark_description=submission.benchmark.description,
        benchmark_manifest_sha256=submission.benchmark.manifest_sha256,
        benchmark_scenario_count=len(submission.benchmark.scenario_hashes),
        trust_level=submission.verification.trust_level,
        evidence_sha256=submission.verification.evidence_sha256,
        github_run_url=submission.verification.github_run_url,
        generated_at=submission.verification.generated_at,
        total_trials=submission.metrics.total_trials,
        final_answer_pass_rate=submission.metrics.final_answer_pass_rate,
        trace_aware_pass_rate=submission.metrics.trace_aware_pass_rate,
        answer_only_missed_failures=submission.metrics.answer_only_missed_failures,
        answer_only_missed_failure_rate=submission.metrics.answer_only_missed_failure_rate,
        outcome_counts=submission.metrics.outcome_counts,
    )


def _rank_rows(rows: list[LeaderboardRow]) -> list[LeaderboardRow]:
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            row.benchmark_name,
            -row.trace_aware_pass_rate,
            row.answer_only_missed_failures,
            -row.final_answer_pass_rate,
            -_trust_priority(row.trust_level),
            row.agent_name.lower(),
            row.agent_version.lower(),
        ),
    )
    ranked: list[LeaderboardRow] = []
    ranks_by_benchmark: dict[str, int] = {}
    for row in sorted_rows:
        rank = ranks_by_benchmark.get(row.benchmark_name, 0) + 1
        ranks_by_benchmark[row.benchmark_name] = rank
        ranked.append(row.model_copy(update={"rank": rank}))
    return ranked


def _trust_priority(trust_level: str) -> int:
    return {
        "maintainer_rerun": 3,
        "github_actions": 2,
        "self_reported": 1,
    }.get(trust_level, 0)


def _write_leaderboard_csv(index: LeaderboardIndex, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rank",
        "agent_name",
        "agent_version",
        "benchmark_name",
        "benchmark_manifest_sha256",
        "benchmark_scenario_count",
        "submission_schema_version",
        "submission_generated_by",
        "trust_level",
        "trace_aware_pass_rate",
        "final_answer_pass_rate",
        "answer_only_missed_failures",
        "answer_only_missed_failure_rate",
        "total_trials",
        "repo_url",
        "commit_sha",
        "github_run_url",
        "evidence_sha256",
        "maintainer_rerun_url",
        "maintainer_rerun_path",
        "maintainer_rerun_evidence_sha256",
        "maintainer_rerun_github_repository",
        "maintainer_rerun_github_sha",
        "maintainer_rerun_generated_at",
        "maintainer_rerun_generated_by",
        "submission_path",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in index.rows:
            writer.writerow(
                {
                    "rank": row.rank,
                    "agent_name": row.agent_name,
                    "agent_version": row.agent_version,
                    "benchmark_name": row.benchmark_name,
                    "benchmark_manifest_sha256": row.benchmark_manifest_sha256,
                    "benchmark_scenario_count": row.benchmark_scenario_count,
                    "submission_schema_version": row.submission_schema_version,
                    "submission_generated_by": row.submission_generated_by,
                    "trust_level": row.trust_level,
                    "trace_aware_pass_rate": f"{row.trace_aware_pass_rate:.1f}",
                    "final_answer_pass_rate": f"{row.final_answer_pass_rate:.1f}",
                    "answer_only_missed_failures": row.answer_only_missed_failures,
                    "answer_only_missed_failure_rate": (
                        f"{row.answer_only_missed_failure_rate:.1f}"
                    ),
                    "total_trials": row.total_trials,
                    "repo_url": row.repo_url,
                    "commit_sha": row.commit_sha,
                    "github_run_url": row.github_run_url,
                    "evidence_sha256": row.evidence_sha256,
                    "maintainer_rerun_url": row.maintainer_rerun_url,
                    "maintainer_rerun_path": row.maintainer_rerun_path,
                    "maintainer_rerun_evidence_sha256": row.maintainer_rerun_evidence_sha256,
                    "maintainer_rerun_github_repository": row.maintainer_rerun_github_repository,
                    "maintainer_rerun_github_sha": row.maintainer_rerun_github_sha,
                    "maintainer_rerun_generated_at": row.maintainer_rerun_generated_at,
                    "maintainer_rerun_generated_by": row.maintainer_rerun_generated_by,
                    "submission_path": row.submission_path,
                }
            )


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


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "agent"
