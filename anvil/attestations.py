from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from anvil.leaderboard import LeaderboardValidationError, validate_leaderboard_submission

ARTIFACT_ATTESTATION_VERIFICATION_SCHEMA_VERSION = (
    "agent-anvil.leaderboard.artifact_attestation_verification.v1"
)
SLSA_PROVENANCE_V1 = "https://slsa.dev/provenance/v1"
DEFAULT_ATTESTATION_TIMEOUT_SECONDS = 30.0
MAX_GH_ERROR_LENGTH = 500


class LeaderboardArtifactAttestationVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["agent-anvil.leaderboard.artifact_attestation_verification.v1"]
    status: Literal["verified"]
    submission_path: str
    agent_name: str
    benchmark_name: str
    trust_level: Literal["github_actions"]
    github_repository: str
    github_sha: str
    github_run_url: str
    subject_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predicate_type: str
    signer_workflow: str = ""
    source_digest: str
    source_ref: str = ""
    self_hosted_runners_denied: bool
    bundle_path: str = ""
    bundle_sha256: str = ""
    verified_attestations: int = Field(ge=1)
    verification_output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: str
    generated_by: str


def verify_leaderboard_artifact_attestation(
    submission_path: str | Path,
    *,
    signer_workflow: str = "",
    source_ref: str = "",
    bundle_path: str | Path | None = None,
    deny_self_hosted_runners: bool = True,
    timeout_seconds: float = DEFAULT_ATTESTATION_TIMEOUT_SECONDS,
) -> LeaderboardArtifactAttestationVerification:
    selected_submission_path = Path(submission_path)
    submission = validate_leaderboard_submission(
        selected_submission_path,
        verify_artifacts=False,
        require_trust_level="github_actions",
    )
    if timeout_seconds <= 0:
        raise LeaderboardValidationError("attestation timeout must be greater than zero")

    gh_executable = shutil.which("gh")
    if gh_executable is None:
        raise LeaderboardValidationError(
            "GitHub CLI is not installed; install gh and authenticate before verifying "
            "artifact attestations"
        )

    selected_bundle_path = Path(bundle_path) if bundle_path is not None else None
    if selected_bundle_path is not None and not selected_bundle_path.is_file():
        raise LeaderboardValidationError(f"attestation bundle not found: {selected_bundle_path}")

    command = _verification_command(
        gh_executable=gh_executable,
        submission_path=selected_submission_path,
        repository=submission.verification.github_repository,
        source_digest=submission.verification.github_sha,
        signer_workflow=signer_workflow,
        source_ref=source_ref,
        bundle_path=selected_bundle_path,
        deny_self_hosted_runners=deny_self_hosted_runners,
    )
    try:
        completed = _run_gh_attestation_verify(command, timeout_seconds=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        raise LeaderboardValidationError(
            "GitHub artifact attestation verification timed out after "
            f"{timeout_seconds:.1f} seconds"
        ) from error
    if completed.returncode != 0:
        detail = _bounded_cli_error(completed.stderr)
        suffix = f": {detail}" if detail else ""
        raise LeaderboardValidationError(f"GitHub artifact attestation verification failed{suffix}")

    verification_results = _load_verification_results(completed.stdout)
    subject_sha256 = _sha256_file(selected_submission_path)
    verified_subject_digests = _verified_subject_sha256_digests(verification_results)
    if subject_sha256 not in verified_subject_digests:
        rendered_digests = ", ".join(sorted(verified_subject_digests)) or "not provided"
        raise LeaderboardValidationError(
            "GitHub artifact attestation subject SHA-256 mismatch: "
            f"expected {subject_sha256}, got {rendered_digests}"
        )

    return LeaderboardArtifactAttestationVerification(
        schema_version=ARTIFACT_ATTESTATION_VERIFICATION_SCHEMA_VERSION,
        status="verified",
        submission_path=str(_display_path(selected_submission_path)),
        agent_name=submission.submitter.agent_name,
        benchmark_name=submission.benchmark.name,
        trust_level="github_actions",
        github_repository=submission.verification.github_repository,
        github_sha=submission.verification.github_sha,
        github_run_url=submission.verification.github_run_url,
        subject_sha256=subject_sha256,
        predicate_type=SLSA_PROVENANCE_V1,
        signer_workflow=signer_workflow,
        source_digest=submission.verification.github_sha,
        source_ref=source_ref,
        self_hosted_runners_denied=deny_self_hosted_runners,
        bundle_path=str(_display_path(selected_bundle_path)) if selected_bundle_path else "",
        bundle_sha256=_sha256_file(selected_bundle_path) if selected_bundle_path else "",
        verified_attestations=len(verification_results),
        verification_output_sha256=hashlib.sha256(completed.stdout.encode()).hexdigest(),
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        generated_by=f"agent-anvil/{_anvil_version()}",
    )


def _verification_command(
    *,
    gh_executable: str,
    submission_path: Path,
    repository: str,
    source_digest: str,
    signer_workflow: str,
    source_ref: str,
    bundle_path: Path | None,
    deny_self_hosted_runners: bool,
) -> list[str]:
    command = [
        gh_executable,
        "attestation",
        "verify",
        str(submission_path),
        "--repo",
        repository,
        "--predicate-type",
        SLSA_PROVENANCE_V1,
        "--source-digest",
        source_digest,
    ]
    if signer_workflow:
        command.extend(["--signer-workflow", signer_workflow])
    if source_ref:
        command.extend(["--source-ref", source_ref])
    if deny_self_hosted_runners:
        command.append("--deny-self-hosted-runners")
    if bundle_path is not None:
        command.extend(["--bundle", str(bundle_path)])
    command.extend(["--format", "json"])
    return command


def _run_gh_attestation_verify(
    command: list[str],
    *,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )


def _load_verification_results(stdout: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise LeaderboardValidationError(
            f"GitHub artifact attestation verification returned invalid JSON: {error}"
        ) from error
    if not isinstance(payload, list):
        raise LeaderboardValidationError(
            "GitHub artifact attestation verification must return a JSON array"
        )
    if not payload:
        raise LeaderboardValidationError(
            "GitHub artifact attestation verification returned no verified attestations"
        )
    if not all(isinstance(item, dict) for item in payload):
        raise LeaderboardValidationError(
            "GitHub artifact attestation verification returned a non-object result"
        )
    return payload


def _verified_subject_sha256_digests(results: list[dict[str, Any]]) -> set[str]:
    digests: set[str] = set()
    for result in results:
        verification_result = result.get("verificationResult")
        if not isinstance(verification_result, dict):
            continue
        statement = verification_result.get("statement")
        if not isinstance(statement, dict):
            continue
        subjects = statement.get("subject")
        if not isinstance(subjects, list):
            continue
        for subject in subjects:
            if not isinstance(subject, dict):
                continue
            digest = subject.get("digest")
            if not isinstance(digest, dict):
                continue
            sha256 = digest.get("sha256")
            if isinstance(sha256, str) and sha256:
                digests.add(sha256.lower())
    return digests


def _bounded_cli_error(stderr: str) -> str:
    normalized = " ".join(stderr.split())
    return normalized[:MAX_GH_ERROR_LENGTH]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> Path:
    try:
        return path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return path


def _anvil_version() -> str:
    try:
        return version("agent-anvil")
    except PackageNotFoundError:
        return "0+unknown"
