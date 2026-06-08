from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

import anvil.leaderboard as leaderboard_module
from anvil.benchmark import run_benchmark
from anvil.cli import app
from anvil.leaderboard import (
    LeaderboardValidationError,
    build_leaderboard_index,
    export_leaderboard_submission,
    generate_leaderboard_reproduction_script,
    inspect_leaderboard_submission,
    prepare_leaderboard_pr_submission,
    validate_leaderboard_submission,
)


def test_export_leaderboard_submission_writes_verifiable_summary(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    out_path = tmp_path / "leaderboard_submission.json"

    submission = export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=out_path,
        agent_name="Support Agent",
        agent_version="demo",
        repo_url="https://github.com/example/support-agent",
        commit_sha="abc123",
    )
    payload = json.loads(out_path.read_text(encoding="utf-8"))

    assert submission.schema_version == "agent-anvil.leaderboard.v1"
    assert payload["submitter"]["agent_name"] == "Support Agent"
    assert payload["submitter"]["repo_url"] == "https://github.com/example/support-agent"
    assert payload["verification"]["trust_level"] == "self_reported"
    assert payload["benchmark"]["name"] == "paper_benchmark"
    assert payload["benchmark"]["manifest_sha256"]
    assert payload["benchmark"]["scenario_hashes"][str(scenario_file)]
    assert payload["metrics"]["total_trials"] == 6
    assert payload["metrics"]["trace_aware_pass_rate"] == 50.0
    assert payload["metrics"]["answer_only_missed_failures"] == 3
    assert payload["artifacts"]["results_json_sha256"]
    assert payload["evaluator_ablation"][0]["evaluator"] == "final_answer_baseline"
    assert "trials" not in payload


def test_cli_leaderboard_export_writes_submission(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    out_path = tmp_path / "leaderboard_submission.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "leaderboard",
            "export",
            str(tmp_path / "paper" / "results.json"),
            "--manifest",
            str(manifest_path),
            "--out",
            str(out_path),
            "--agent-name",
            "Support Agent",
            "--agent-version",
            "demo",
            "--repo-url",
            "https://github.com/example/support-agent",
            "--commit-sha",
            "abc123",
        ],
    )

    assert result.exit_code == 0
    assert f"Wrote leaderboard submission: {out_path}" in result.stdout
    assert "Trust level: self_reported" in result.stdout
    assert "Trace-aware pass rate: 50.0%" in result.stdout
    assert out_path.exists()


def test_validate_leaderboard_submission_rejects_tampering(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    out_path = tmp_path / "leaderboard_submission.json"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=out_path,
        agent_name="Support Agent",
    )
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    payload["metrics"]["trace_aware_pass_rate"] = 99.0
    out_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LeaderboardValidationError, match="evidence hash mismatch"):
        validate_leaderboard_submission(out_path)


def test_cli_leaderboard_validate_checks_artifact_hashes(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    out_path = tmp_path / "leaderboard_submission.json"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=out_path,
        agent_name="Support Agent",
    )
    runner = CliRunner()

    valid = runner.invoke(app, ["leaderboard", "validate", str(out_path)])

    assert valid.exit_code == 0
    assert "Leaderboard submission is valid" in valid.stdout

    (tmp_path / "paper" / "results.json").write_text("{}", encoding="utf-8")
    invalid = runner.invoke(app, ["leaderboard", "validate", str(out_path)])

    assert invalid.exit_code == 1
    assert "artifact hash mismatch" in invalid.stderr


@pytest.mark.parametrize(
    "submission_body",
    [
        "{",
        "{}",
    ],
)
def test_cli_leaderboard_validate_reports_invalid_submission_without_traceback(
    tmp_path: Path,
    submission_body: str,
) -> None:
    submission_path = tmp_path / "leaderboard_submission.json"
    submission_path.write_text(submission_body, encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(app, ["leaderboard", "validate", str(submission_path)])

    assert result.exit_code == 1
    assert "invalid leaderboard submission" in result.stderr
    assert str(submission_path) in result.stderr
    assert "Traceback" not in result.stderr


def test_inspect_leaderboard_submission_writes_reviewable_trust_report(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    out_path = tmp_path / "leaderboard_submission.json"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=out_path,
        agent_name="Support Agent",
        agent_version="demo",
        repo_url="https://github.com/example/support-agent",
        commit_sha="abc123",
    )

    inspection = inspect_leaderboard_submission(out_path, verify_artifacts=True)

    assert inspection.artifact_status == "verified"
    assert inspection.warning_count == 1
    assert "Agent: Support Agent (demo)" in inspection.markdown
    assert "Trust level: self_reported" in inspection.markdown
    assert "Artifact hashes: verified" in inspection.markdown
    assert "git clone https://github.com/example/support-agent" in inspection.markdown
    assert "git checkout abc123" in inspection.markdown
    assert f"uv run anvil paper reproduce --manifest {manifest_path}" in inspection.markdown
    assert "self-reported; prefer a github_actions or maintainer_rerun row" in inspection.markdown


def test_cli_leaderboard_inspect_can_write_markdown_report(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    submission_path = tmp_path / "leaderboard_submission.json"
    report_path = tmp_path / "leaderboard_inspection.md"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=submission_path,
        agent_name="Support Agent",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "leaderboard",
            "inspect",
            str(submission_path),
            "--no-artifacts",
            "--out",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert f"Wrote leaderboard inspection: {report_path}" in result.stdout
    assert "Artifact hashes: not checked" in result.stdout
    report = report_path.read_text(encoding="utf-8")
    assert "## Reproducibility Checklist" in report
    assert "Artifact hashes: not checked" in report


def test_generate_leaderboard_reproduction_script_writes_reviewable_shell_script(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    submission_path = tmp_path / "leaderboard_submission.json"
    script_path = tmp_path / "reproduce.sh"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=submission_path,
        agent_name="Support Agent",
        agent_version="demo",
        repo_url="https://github.com/example/support-agent.git",
        commit_sha="abc123",
    )

    script = generate_leaderboard_reproduction_script(
        submission_path,
        out_path=script_path,
    )

    assert script.path == script_path
    assert script_path.read_text(encoding="utf-8") == script.content
    assert script_path.stat().st_mode & 0o111
    assert "git clone https://github.com/example/support-agent.git source" in script.content
    assert "git checkout abc123" in script.content
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    assert f"agent-anvil@v{version}" in script.content
    assert f"anvil paper reproduce --manifest {manifest_path}" in script.content
    assert "--agent-name 'Support Agent'" in script.content
    assert "evidence_sha256" in script.content
    assert "reproduction check passed" in script.content


def test_generate_leaderboard_reproduction_script_requires_source_revision(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    submission_path = tmp_path / "leaderboard_submission.json"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=submission_path,
        agent_name="Support Agent",
    )

    with pytest.raises(LeaderboardValidationError, match="repo_url and commit_sha"):
        generate_leaderboard_reproduction_script(submission_path, out_path=tmp_path / "r.sh")


def test_cli_leaderboard_reproduce_writes_script(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    submission_path = tmp_path / "leaderboard_submission.json"
    script_path = tmp_path / "reproduce.sh"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=submission_path,
        agent_name="Support Agent",
        repo_url="https://github.com/example/support-agent",
        commit_sha="abc123",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "leaderboard",
            "reproduce",
            str(submission_path),
            "--out",
            str(script_path),
        ],
    )

    assert result.exit_code == 0
    assert f"Wrote leaderboard reproduction script: {script_path}" in result.stdout
    assert "Review before executing" in result.stdout
    assert "git clone https://github.com/example/support-agent source" in script_path.read_text(
        encoding="utf-8"
    )


def test_export_leaderboard_submission_marks_github_actions_trust(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "agent-axiom/agent-anvil")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    out_path = tmp_path / "leaderboard_submission.json"

    submission = export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=out_path,
        agent_name="Support Agent",
    )

    assert submission.verification.trust_level == "github_actions"
    assert submission.verification.github_run_url == (
        "https://github.com/agent-axiom/agent-anvil/actions/runs/12345"
    )
    assert submission.submitter.commit_sha == "abc123"


def test_validate_leaderboard_submission_rejects_github_actions_commit_sha_mismatch(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "agent-axiom/agent-anvil")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    out_path = tmp_path / "leaderboard_submission.json"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=out_path,
        agent_name="Support Agent",
        commit_sha="def456",
    )

    with pytest.raises(LeaderboardValidationError, match=r"submitter\.commit_sha"):
        validate_leaderboard_submission(out_path, verify_artifacts=False)


@pytest.mark.parametrize(
    ("field", "match"),
    [
        ("github_run_url", "verification.github_run_url"),
        ("github_repository", "verification.github_repository"),
        ("github_sha", "verification.github_sha"),
    ],
)
def test_validate_leaderboard_submission_rejects_github_actions_without_ci_metadata(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    match: str,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    out_path = tmp_path / "leaderboard_submission.json"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=out_path,
        agent_name="Support Agent",
    )
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    payload["verification"]["trust_level"] = "github_actions"
    payload["verification"]["github_run_url"] = (
        "https://github.com/agent-axiom/agent-anvil/actions/runs/12345"
    )
    payload["verification"]["github_repository"] = "agent-axiom/agent-anvil"
    payload["verification"]["github_sha"] = "abc123"
    payload["verification"][field] = ""
    out_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LeaderboardValidationError, match=match):
        validate_leaderboard_submission(out_path, verify_artifacts=False)


def test_validate_leaderboard_submission_rejects_github_actions_run_url_repo_mismatch(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    out_path = tmp_path / "leaderboard_submission.json"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=out_path,
        agent_name="Support Agent",
    )
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    payload["verification"]["trust_level"] = "github_actions"
    payload["verification"]["github_run_url"] = "https://github.com/other/repo/actions/runs/12345"
    payload["verification"]["github_repository"] = "agent-axiom/agent-anvil"
    payload["verification"]["github_sha"] = "abc123"
    out_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LeaderboardValidationError, match=r"verification\.github_run_url"):
        validate_leaderboard_submission(out_path, verify_artifacts=False)


def test_validate_leaderboard_submission_can_verify_github_actions_run(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    def fake_fetch(
        repository: str,
        run_id: str,
        *,
        token: str | None = None,
        host: str = "github.com",
    ) -> dict[str, object]:
        assert repository == "agent-axiom/agent-anvil"
        assert run_id == "12345"
        assert token is None
        assert host == "github.com"
        return _github_run_payload()

    monkeypatch.setattr(leaderboard_module, "_fetch_github_actions_run", fake_fetch, raising=False)

    submission = validate_leaderboard_submission(
        submission_path,
        verify_artifacts=False,
        verify_github_run=True,
    )

    assert submission.verification.trust_level == "github_actions"


def test_validate_leaderboard_submission_rejects_failed_github_actions_run(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    def fake_fetch(
        _repository: str,
        _run_id: str,
        **_kwargs: object,
    ) -> dict[str, object]:
        return _github_run_payload(conclusion="failure")

    monkeypatch.setattr(leaderboard_module, "_fetch_github_actions_run", fake_fetch, raising=False)

    with pytest.raises(LeaderboardValidationError, match="GitHub Actions run conclusion"):
        validate_leaderboard_submission(
            submission_path,
            verify_artifacts=False,
            verify_github_run=True,
        )


@pytest.mark.parametrize(
    "github_run_url",
    [
        "/agent-axiom/agent-anvil/actions/runs/12345",
        "http://github.com/agent-axiom/agent-anvil/actions/runs/12345",
    ],
)
def test_validate_leaderboard_submission_rejects_non_https_absolute_github_run_url(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    github_run_url: str,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    payload = json.loads(submission_path.read_text(encoding="utf-8"))
    payload["verification"]["github_run_url"] = github_run_url
    submission_path.write_text(json.dumps(payload), encoding="utf-8")

    def fake_fetch(
        _repository: str,
        _run_id: str,
        **_kwargs: object,
    ) -> dict[str, object]:
        raise AssertionError("invalid run URL should be rejected before API fetch")

    monkeypatch.setattr(leaderboard_module, "_fetch_github_actions_run", fake_fetch, raising=False)

    with pytest.raises(LeaderboardValidationError, match="absolute HTTPS"):
        validate_leaderboard_submission(
            submission_path,
            verify_artifacts=False,
            verify_github_run=True,
        )


def test_cli_leaderboard_validate_can_verify_github_actions_run(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    def fake_fetch(
        _repository: str,
        _run_id: str,
        **_kwargs: object,
    ) -> dict[str, object]:
        return _github_run_payload()

    monkeypatch.setattr(leaderboard_module, "_fetch_github_actions_run", fake_fetch, raising=False)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "leaderboard",
            "validate",
            str(submission_path),
            "--no-artifacts",
            "--github-run",
        ],
    )

    assert result.exit_code == 0
    assert "GitHub run: verified" in result.stdout


def test_inspect_leaderboard_submission_reports_failed_github_actions_run_without_abort(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    def fake_fetch(
        _repository: str,
        _run_id: str,
        **_kwargs: object,
    ) -> dict[str, object]:
        return _github_run_payload(conclusion="failure")

    monkeypatch.setattr(leaderboard_module, "_fetch_github_actions_run", fake_fetch, raising=False)

    inspection = inspect_leaderboard_submission(
        submission_path,
        verify_artifacts=False,
        verify_github_run=True,
    )

    assert inspection.github_run_status == "failed"
    assert "GitHub run verification failed" in inspection.warnings[0]
    assert "- GitHub run verification: failed" in inspection.markdown
    assert "- GitHub run error: GitHub Actions run conclusion mismatch" in inspection.markdown


def test_build_leaderboard_index_can_verify_github_actions_runs(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    submissions_dir = tmp_path / "submissions"
    submissions_dir.mkdir()
    shutil.copyfile(submission_path, submissions_dir / "support-agent.json")

    def fake_fetch(
        _repository: str,
        _run_id: str,
        **_kwargs: object,
    ) -> dict[str, object]:
        return _github_run_payload()

    monkeypatch.setattr(leaderboard_module, "_fetch_github_actions_run", fake_fetch, raising=False)

    index = build_leaderboard_index(
        submissions_dir,
        verify_artifacts=False,
        verify_github_run=True,
    )

    assert index.rows[0].trust_level == "github_actions"


def test_prepare_leaderboard_pr_submission_rejects_failed_github_actions_run(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submission_path = _write_github_actions_submission(
        scenario_file=scenario_file,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    def fake_fetch(
        _repository: str,
        _run_id: str,
        **_kwargs: object,
    ) -> dict[str, object]:
        return _github_run_payload(head_sha="other-sha")

    monkeypatch.setattr(leaderboard_module, "_fetch_github_actions_run", fake_fetch, raising=False)

    with pytest.raises(LeaderboardValidationError, match="GitHub Actions run head_sha"):
        prepare_leaderboard_pr_submission(
            submission_path=submission_path,
            leaderboard_repo=tmp_path / "leaderboard",
            verify_github_run=True,
        )


def test_build_leaderboard_index_writes_ranked_csv_and_json(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    submissions_dir = tmp_path / "submissions"
    submissions_dir.mkdir()
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=submissions_dir / "support-agent.json",
        agent_name="Support Agent",
        agent_version="demo",
    )
    better_results = tmp_path / "paper" / "better-results.json"
    _write_better_result(tmp_path / "paper" / "results.json", better_results)
    export_leaderboard_submission(
        results_json=better_results,
        manifest_path=manifest_path,
        out_path=submissions_dir / "better-agent.json",
        agent_name="Better Agent",
        agent_version="patched",
    )
    csv_path = tmp_path / "leaderboard.csv"
    json_path = tmp_path / "leaderboard.json"

    index = build_leaderboard_index(
        submissions_dir,
        csv_path=csv_path,
        json_path=json_path,
        verify_artifacts=True,
    )
    csv_text = csv_path.read_text(encoding="utf-8")
    json_payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert index.schema_version == "agent-anvil.leaderboard.index.v1"
    assert [row.agent_name for row in index.rows] == ["Better Agent", "Support Agent"]
    assert [row.rank for row in index.rows] == [1, 2]
    assert index.rows[0].trace_aware_pass_rate == 83.3
    assert (
        "rank,agent_name,agent_version,benchmark_name,benchmark_manifest_sha256,"
        "benchmark_scenario_count,submission_schema_version,submission_generated_by,"
        "trust_level"
    ) in csv_text
    assert "Better Agent,patched,paper_benchmark," in csv_text
    assert ",1,agent-anvil.leaderboard.v1,agent-anvil/" in csv_text
    assert json_payload["rows"][0]["agent_name"] == "Better Agent"
    assert json_payload["rows"][0]["submission_path"].endswith("better-agent.json")
    assert json_payload["rows"][0]["submission_schema_version"] == "agent-anvil.leaderboard.v1"
    assert json_payload["rows"][0]["submission_generated_by"].startswith("agent-anvil/")
    assert json_payload["rows"][0]["benchmark_manifest_sha256"]
    assert json_payload["rows"][0]["benchmark_scenario_count"] == 1


def test_cli_leaderboard_build_writes_index_files(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    submissions_dir = tmp_path / "submissions"
    submissions_dir.mkdir()
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=submissions_dir / "support-agent.json",
        agent_name="Support Agent",
    )
    csv_path = tmp_path / "leaderboard.csv"
    json_path = tmp_path / "leaderboard.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "leaderboard",
            "build",
            str(submissions_dir),
            "--out",
            str(csv_path),
            "--json-out",
            str(json_path),
            "--artifacts",
        ],
    )

    assert result.exit_code == 0
    assert "Wrote leaderboard CSV:" in result.stdout
    assert "Rows: 1" in result.stdout
    assert csv_path.exists()
    assert json_path.exists()


def test_build_leaderboard_index_rejects_duplicate_evidence_hash(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    submissions_dir = tmp_path / "submissions"
    submissions_dir.mkdir()
    first = submissions_dir / "support-agent.json"
    duplicate = submissions_dir / "duplicate.json"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=first,
        agent_name="Support Agent",
    )
    shutil.copyfile(first, duplicate)

    with pytest.raises(LeaderboardValidationError, match="duplicate evidence hash"):
        build_leaderboard_index(submissions_dir, verify_artifacts=True)


def test_prepare_leaderboard_pr_submission_copies_slugged_file(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    submission_path = tmp_path / "leaderboard_submission.json"
    leaderboard_repo = tmp_path / "leaderboard"
    (leaderboard_repo / "submissions").mkdir(parents=True)
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=submission_path,
        agent_name="Support Agent!",
        agent_version="demo",
    )

    prepared = prepare_leaderboard_pr_submission(
        submission_path=submission_path,
        leaderboard_repo=leaderboard_repo,
    )

    assert prepared.target_path == leaderboard_repo / "submissions" / "support-agent.json"
    assert prepared.target_path.read_text(encoding="utf-8") == submission_path.read_text(
        encoding="utf-8"
    )
    assert prepared.submission.submitter.agent_name == "Support Agent!"
    assert prepared.branch_name == "add-support-agent-submission"
    assert prepared.commit_message == "Add support-agent leaderboard submission"
    assert prepared.pr_title == "Add Support Agent! leaderboard submission"
    assert "Trace-aware pass rate: 50.0%" in prepared.pr_body
    assert "git checkout -b add-support-agent-submission" in prepared.next_steps
    assert "git push --set-upstream origin add-support-agent-submission" in prepared.next_steps
    assert "--head add-support-agent-submission" in prepared.next_steps
    assert "gh pr create" in prepared.next_steps


def test_prepare_leaderboard_pr_submission_writes_reviewable_pr_body(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "agent-axiom/agent-anvil")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    submission_path = tmp_path / "leaderboard_submission.json"
    leaderboard_repo = tmp_path / "leaderboard"
    pr_body_path = tmp_path / "agent-anvil-leaderboard-pr.md"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=submission_path,
        agent_name="Support Agent",
        repo_url="https://github.com/agent-axiom/agent-anvil",
    )

    prepared = prepare_leaderboard_pr_submission(
        submission_path=submission_path,
        leaderboard_repo=leaderboard_repo,
        require_trust_level="github_actions",
        pr_body_out=pr_body_path,
    )

    pr_body = pr_body_path.read_text(encoding="utf-8")
    assert prepared.pr_body == pr_body
    assert "## Agent Anvil leaderboard submission" in pr_body
    assert "- Agent: Support Agent" in pr_body
    assert "- Trust level: github_actions" in pr_body
    assert "- GitHub run: https://github.com/agent-axiom/agent-anvil/actions/runs/12345" in pr_body
    assert "- Evidence SHA-256:" in pr_body
    assert (
        "uv run anvil leaderboard validate submissions/support-agent.json --no-artifacts" in pr_body
    )
    assert (
        "gh attestation verify submissions/support-agent.json -R agent-axiom/agent-anvil" in pr_body
    )
    assert "does not execute arbitrary user code" in pr_body
    assert "gh pr create" in prepared.next_steps


def test_prepare_leaderboard_pr_submission_refuses_existing_file(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    submission_path = tmp_path / "leaderboard_submission.json"
    leaderboard_repo = tmp_path / "leaderboard"
    submissions_dir = leaderboard_repo / "submissions"
    submissions_dir.mkdir(parents=True)
    (submissions_dir / "support-agent.json").write_text("{}", encoding="utf-8")
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=submission_path,
        agent_name="Support Agent",
    )

    with pytest.raises(LeaderboardValidationError, match="already exists"):
        prepare_leaderboard_pr_submission(
            submission_path=submission_path,
            leaderboard_repo=leaderboard_repo,
        )


def test_cli_leaderboard_pr_prepares_submission_file(
    scenario_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_github_env(monkeypatch)
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    submission_path = tmp_path / "leaderboard_submission.json"
    leaderboard_repo = tmp_path / "leaderboard"
    pr_body_path = tmp_path / "pr-body.md"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=submission_path,
        agent_name="Support Agent",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "leaderboard",
            "pr",
            str(submission_path),
            "--leaderboard-repo",
            str(leaderboard_repo),
            "--pr-body-out",
            str(pr_body_path),
        ],
    )

    assert result.exit_code == 0
    assert "Prepared leaderboard PR file:" in result.stdout
    assert f"Wrote leaderboard PR body: {pr_body_path}" in result.stdout
    assert "submissions/support-agent.json" in result.stdout
    assert "git checkout -b add-support-agent-submission" in result.stdout
    assert (leaderboard_repo / "submissions" / "support-agent.json").exists()
    assert "## Agent Anvil leaderboard submission" in pr_body_path.read_text(encoding="utf-8")


def _clear_github_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "GITHUB_ACTIONS",
        "GITHUB_SERVER_URL",
        "GITHUB_REPOSITORY",
        "GITHUB_RUN_ID",
        "GITHUB_SHA",
    ):
        monkeypatch.delenv(name, raising=False)


def _write_better_result(source_path: Path, out_path: Path) -> None:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    payload["trace_aware_passed"] = 5
    payload["trace_aware_pass_rate"] = 83.3
    payload["trace_aware_pass_rate_ci_low"] = 43.6
    payload["trace_aware_pass_rate_ci_high"] = 97.0
    payload["answer_only_missed_failures"] = 1
    payload["answer_only_missed_failure_rate"] = 16.7
    payload["answer_only_missed_failure_rate_ci_low"] = 3.0
    payload["answer_only_missed_failure_rate_ci_high"] = 56.4
    out_path.write_text(json.dumps(payload), encoding="utf-8")


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
    manifest_path = _write_manifest(tmp_path, scenario_file)
    run_benchmark(manifest_path, offline=True, runs_dir=tmp_path / "runs")
    out_path = tmp_path / "leaderboard_submission.json"
    export_leaderboard_submission(
        results_json=tmp_path / "paper" / "results.json",
        manifest_path=manifest_path,
        out_path=out_path,
        agent_name="Support Agent",
        repo_url="https://github.com/agent-axiom/agent-anvil",
    )
    return out_path


def _github_run_payload(
    *,
    status: str = "completed",
    conclusion: str | None = "success",
    head_sha: str = "abc123",
    repository: str = "agent-axiom/agent-anvil",
) -> dict[str, object]:
    return {
        "status": status,
        "conclusion": conclusion,
        "head_sha": head_sha,
        "html_url": "https://github.com/agent-axiom/agent-anvil/actions/runs/12345",
        "repository": {
            "full_name": repository,
        },
    }


def _write_manifest(tmp_path: Path, scenario_file: Path) -> Path:
    manifest_path = tmp_path / "paper.yaml"
    manifest_path.write_text(
        f"""
name: paper_benchmark
suites:
  - {scenario_file}
output:
  json: {tmp_path / "paper" / "results.json"}
  markdown: {tmp_path / "paper" / "results.md"}
  tables: {tmp_path / "paper" / "tables"}
""",
        encoding="utf-8",
    )
    return manifest_path
