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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
    next_steps: str


@dataclass(frozen=True)
class LeaderboardInspection:
    submission: LeaderboardSubmission
    artifact_status: Literal["verified", "not checked", "failed"]
    artifact_error: str
    warnings: tuple[str, ...]
    markdown: str

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


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


def inspect_leaderboard_submission(
    submission_path: str | Path,
    *,
    verify_artifacts: bool = True,
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

    warnings = tuple(_inspection_warnings(submission, artifact_status, artifact_error))
    markdown = _inspection_markdown(
        submission=submission,
        artifact_status=artifact_status,
        artifact_error=artifact_error,
        warnings=warnings,
    )
    return LeaderboardInspection(
        submission=submission,
        artifact_status=artifact_status,
        artifact_error=artifact_error,
        warnings=warnings,
        markdown=markdown,
    )


def build_leaderboard_index(
    submissions_dir: str | Path,
    *,
    csv_path: str | Path | None = None,
    json_path: str | Path | None = None,
    verify_artifacts: bool = False,
    require_trust_level: str | None = None,
) -> LeaderboardIndex:
    selected_submissions_dir = Path(submissions_dir)
    submissions = _load_submission_files(
        selected_submissions_dir,
        verify_artifacts=verify_artifacts,
        require_trust_level=require_trust_level,
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
    force: bool = False,
    require_trust_level: str | None = None,
) -> LeaderboardPrPreparation:
    selected_submission_path = Path(submission_path)
    selected_leaderboard_repo = Path(leaderboard_repo)
    submission = validate_leaderboard_submission(
        selected_submission_path,
        verify_artifacts=False,
        require_trust_level=require_trust_level,
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
    return LeaderboardPrPreparation(
        submission=submission,
        target_path=target_path,
        next_steps=_leaderboard_pr_next_steps(
            target_path=target_path,
            leaderboard_repo=selected_leaderboard_repo,
            slug=target_path.stem,
        ),
    )


def _inspection_warnings(
    submission: LeaderboardSubmission,
    artifact_status: str,
    artifact_error: str,
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
    return warnings


def _inspection_markdown(
    *,
    submission: LeaderboardSubmission,
    artifact_status: str,
    artifact_error: str,
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
        f"- Artifact hashes: {artifact_status}",
    ]
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
    slug: str,
) -> str:
    display_target = target_path.relative_to(leaderboard_repo)
    return "\n".join(
        [
            f"cd {leaderboard_repo}",
            f"git checkout -b add-{slug}-submission",
            f"git add {display_target}",
            f'git commit -m "Add {slug} leaderboard submission"',
            "gh pr create --fill --repo agent-axiom/agent-anvil-leaderboard",
        ]
    )


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
