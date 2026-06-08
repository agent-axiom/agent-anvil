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
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from anvil.benchmark import (
    BenchmarkAblationResult,
    BenchmarkResult,
    load_benchmark_manifest,
)

LEADERBOARD_SCHEMA_VERSION = "agent-anvil.leaderboard.v1"
LEADERBOARD_INDEX_SCHEMA_VERSION = "agent-anvil.leaderboard.index.v1"


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


def build_leaderboard_index(
    submissions_dir: str | Path,
    *,
    csv_path: str | Path | None = None,
    json_path: str | Path | None = None,
    verify_artifacts: bool = False,
    require_trust_level: str | None = None,
    verify_github_run: bool = False,
) -> LeaderboardIndex:
    selected_submissions_dir = Path(submissions_dir)
    submissions = _load_submission_files(
        selected_submissions_dir,
        verify_artifacts=verify_artifacts,
        require_trust_level=require_trust_level,
        verify_github_run=verify_github_run,
    )
    rows = _rank_rows(
        [
            _row_from_submission(submission_path, submission)
            for submission_path, submission in submissions
        ]
    )
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
