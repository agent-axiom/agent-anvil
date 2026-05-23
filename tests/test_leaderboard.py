from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from anvil.benchmark import run_benchmark
from anvil.cli import app
from anvil.leaderboard import (
    LeaderboardValidationError,
    build_leaderboard_index,
    export_leaderboard_submission,
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
    assert "rank,agent_name,agent_version,benchmark_name,trust_level" in csv_text
    assert "Better Agent,patched,paper_benchmark,self_reported" in csv_text
    assert json_payload["rows"][0]["agent_name"] == "Better Agent"
    assert json_payload["rows"][0]["submission_path"].endswith("better-agent.json")


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
    assert "git checkout -b add-support-agent-submission" in prepared.next_steps
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
        ],
    )

    assert result.exit_code == 0
    assert "Prepared leaderboard PR file:" in result.stdout
    assert "submissions/support-agent.json" in result.stdout
    assert "git checkout -b add-support-agent-submission" in result.stdout
    assert (leaderboard_repo / "submissions" / "support-agent.json").exists()


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
