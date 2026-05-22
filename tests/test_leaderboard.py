from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from anvil.benchmark import run_benchmark
from anvil.cli import app
from anvil.leaderboard import (
    LeaderboardValidationError,
    export_leaderboard_submission,
    validate_leaderboard_submission,
)


def test_export_leaderboard_submission_writes_verifiable_summary(
    scenario_file: Path,
    tmp_path: Path,
) -> None:
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
) -> None:
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
) -> None:
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
) -> None:
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
