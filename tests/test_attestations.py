from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

import anvil.attestations as attestations_module
from anvil.attestations import verify_leaderboard_artifact_attestation
from anvil.benchmark import run_benchmark
from anvil.cli import app
from anvil.leaderboard import LeaderboardValidationError, export_leaderboard_submission


def test_verify_artifact_attestation_binds_repo_source_and_subject(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    subject_sha256 = _sha256_file(submission_path)
    bundle_path = tmp_path / "attestation-bundle.jsonl"
    bundle_path.write_text("signed bundle\n", encoding="utf-8")
    commands: list[list[str]] = []

    monkeypatch.setattr(attestations_module.shutil, "which", lambda _name: "/usr/bin/gh")

    def fake_run(command: list[str], *, timeout_seconds: float) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        assert timeout_seconds == 12.5
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=_verification_output(subject_sha256),
            stderr="",
        )

    monkeypatch.setattr(attestations_module, "_run_gh_attestation_verify", fake_run)

    report = verify_leaderboard_artifact_attestation(
        submission_path,
        signer_workflow="agent-axiom/agent-anvil/.github/workflows/leaderboard.yml",
        source_ref="refs/heads/main",
        bundle_path=bundle_path,
        timeout_seconds=12.5,
    )

    assert report.schema_version == ("agent-anvil.leaderboard.artifact_attestation_verification.v1")
    assert report.status == "verified"
    assert report.github_repository == "agent-axiom/agent-anvil"
    assert report.github_sha == "abc123"
    assert report.subject_sha256 == subject_sha256
    assert report.verified_attestations == 1
    assert report.self_hosted_runners_denied is True
    assert report.bundle_sha256 == _sha256_file(bundle_path)
    assert (
        report.verification_output_sha256
        == hashlib.sha256(_verification_output(subject_sha256).encode()).hexdigest()
    )
    assert commands == [
        [
            "/usr/bin/gh",
            "attestation",
            "verify",
            str(submission_path),
            "--repo",
            "agent-axiom/agent-anvil",
            "--predicate-type",
            "https://slsa.dev/provenance/v1",
            "--source-digest",
            "abc123",
            "--signer-workflow",
            "agent-axiom/agent-anvil/.github/workflows/leaderboard.yml",
            "--source-ref",
            "refs/heads/main",
            "--deny-self-hosted-runners",
            "--bundle",
            str(bundle_path),
            "--format",
            "json",
        ]
    ]


def test_verify_artifact_attestation_reports_missing_github_cli(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    monkeypatch.setattr(attestations_module.shutil, "which", lambda _name: None)

    with pytest.raises(LeaderboardValidationError, match=r"GitHub CLI.*not installed"):
        verify_leaderboard_artifact_attestation(submission_path)


def test_verify_artifact_attestation_reports_timeout(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    monkeypatch.setattr(attestations_module.shutil, "which", lambda _name: "/usr/bin/gh")

    def timeout_run(
        command: list[str], *, timeout_seconds: float
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, timeout_seconds)

    monkeypatch.setattr(attestations_module, "_run_gh_attestation_verify", timeout_run)

    with pytest.raises(LeaderboardValidationError, match=r"timed out after 3\.0 seconds"):
        verify_leaderboard_artifact_attestation(submission_path, timeout_seconds=3.0)


def test_verify_artifact_attestation_reports_bounded_cli_failure(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    monkeypatch.setattr(attestations_module.shutil, "which", lambda _name: "/usr/bin/gh")

    def failed_run(
        command: list[str], *, timeout_seconds: float
    ) -> subprocess.CompletedProcess[str]:
        del timeout_seconds
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="x" * 900)

    monkeypatch.setattr(attestations_module, "_run_gh_attestation_verify", failed_run)

    with pytest.raises(LeaderboardValidationError) as error:
        verify_leaderboard_artifact_attestation(submission_path)

    assert "GitHub artifact attestation verification failed" in str(error.value)
    assert len(str(error.value)) < 700


@pytest.mark.parametrize(
    ("stdout", "match"),
    [
        ("not-json", "invalid JSON"),
        ("{}", "JSON array"),
        ("[]", "no verified attestations"),
    ],
)
def test_verify_artifact_attestation_rejects_invalid_verification_output(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    match: str,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    monkeypatch.setattr(attestations_module.shutil, "which", lambda _name: "/usr/bin/gh")

    def fake_run(command: list[str], *, timeout_seconds: float) -> subprocess.CompletedProcess[str]:
        del timeout_seconds
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(attestations_module, "_run_gh_attestation_verify", fake_run)

    with pytest.raises(LeaderboardValidationError, match=match):
        verify_leaderboard_artifact_attestation(submission_path)


def test_verify_artifact_attestation_rejects_subject_digest_mismatch(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    monkeypatch.setattr(attestations_module.shutil, "which", lambda _name: "/usr/bin/gh")

    def fake_run(command: list[str], *, timeout_seconds: float) -> subprocess.CompletedProcess[str]:
        del timeout_seconds
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=_verification_output("0" * 64),
            stderr="",
        )

    monkeypatch.setattr(attestations_module, "_run_gh_attestation_verify", fake_run)

    with pytest.raises(LeaderboardValidationError, match="subject SHA-256 mismatch"):
        verify_leaderboard_artifact_attestation(submission_path)


def test_cli_leaderboard_verify_attestation_writes_stable_report(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    subject_sha256 = _sha256_file(submission_path)
    report_path = tmp_path / "artifact_attestation_verification.json"
    monkeypatch.setattr(attestations_module.shutil, "which", lambda _name: "/usr/bin/gh")

    def fake_run(command: list[str], *, timeout_seconds: float) -> subprocess.CompletedProcess[str]:
        del timeout_seconds
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=_verification_output(subject_sha256),
            stderr="",
        )

    monkeypatch.setattr(attestations_module, "_run_gh_attestation_verify", fake_run)
    result = CliRunner().invoke(
        app,
        [
            "leaderboard",
            "verify-attestation",
            str(submission_path),
            "--out",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert "GitHub artifact attestation is verified" in result.stdout
    assert f"Wrote artifact attestation verification report: {report_path}" in result.stdout
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == (
        "agent-anvil.leaderboard.artifact_attestation_verification.v1"
    )
    assert payload["subject_sha256"] == subject_sha256


def _write_github_actions_submission(
    *,
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "agent-axiom/agent-anvil")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    manifest_path = tmp_path / "paper.yaml"
    manifest_path.write_text(
        f"""
name: attestation_test
suites:
  - {scenario_file}
output:
  json: {tmp_path / "paper" / "results.json"}
  markdown: {tmp_path / "paper" / "results.md"}
  tables: {tmp_path / "paper" / "tables"}
""",
        encoding="utf-8",
    )
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    submission_path = tmp_path / "leaderboard_submission.json"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=submission_path,
        agent_name="Support Agent",
        repo_url="https://github.com/agent-axiom/agent-anvil",
    )
    return submission_path


def _verification_output(subject_sha256: str) -> str:
    return json.dumps(
        [
            {
                "attestation": {"bundle": "omitted by Agent Anvil"},
                "verificationResult": {
                    "statement": {
                        "subject": [
                            {
                                "name": "leaderboard_submission.json",
                                "digest": {"sha256": subject_sha256},
                            }
                        ],
                        "predicateType": "https://slsa.dev/provenance/v1",
                    }
                },
            }
        ]
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
