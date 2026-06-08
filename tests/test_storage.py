from __future__ import annotations

import json
from hashlib import sha256

import pytest
from pydantic import ValidationError

from anvil.grading import GradeResult, SemanticGrade
from anvil.storage import (
    ResultsArtifactError,
    RunManifestError,
    RunManifestPayload,
    load_results,
    validate_run_manifest,
    write_results,
)


def test_write_results_persists_flaky_scenario_summary(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    grades = [
        GradeResult(
            scenario_id="refund_missing_order_id",
            trial=1,
            passed=True,
            deterministic_passed=True,
            semantic=SemanticGrade(passed=True, score=1.0),
            trace_path="runs/test/traces/refund_missing_order_id_trial_1.json",
        ),
        GradeResult(
            scenario_id="refund_missing_order_id",
            trial=2,
            passed=False,
            deterministic_passed=False,
            semantic=SemanticGrade(
                passed=False,
                score=0.2,
                failure_type="premature_tool_execution",
                severity="high",
            ),
            trace_path="runs/test/traces/refund_missing_order_id_trial_2.json",
        ),
        GradeResult(
            scenario_id="refund_valid_order",
            trial=1,
            passed=True,
            deterministic_passed=True,
            semantic=SemanticGrade(passed=True, score=1.0),
            trace_path="runs/test/traces/refund_valid_order_trial_1.json",
        ),
    ]

    results_path = write_results(
        run_dir=run_dir,
        suite_name="refund_agent_regression_suite",
        run_id="run_test",
        total_scenarios=2,
        grades=grades,
        clusters=[],
    )

    payload = json.loads(results_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "anvil.results.v1"
    assert payload["summary"]["flaky_scenarios"] == [
        {
            "scenario_id": "refund_missing_order_id",
            "passed_trials": 1,
            "failed_trials": 1,
            "total_trials": 2,
            "pass_rate": 50.0,
        }
    ]


def test_load_results_accepts_legacy_unversioned_results(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    (run_dir / "results.json").write_text(
        json.dumps(
            {
                "suite": "legacy_suite",
                "run_id": "legacy_run",
                "summary": {"pass_rate": 100.0},
                "grades": [],
                "clusters": [],
            }
        ),
        encoding="utf-8",
    )

    payload = load_results(run_dir)

    assert payload["suite"] == "legacy_suite"
    assert "schema_version" not in payload


def test_load_results_rejects_invalid_versioned_results(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    (run_dir / "results.json").write_text(
        json.dumps(
            {
                "schema_version": "anvil.results.v1",
                "suite": "broken_suite",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ResultsArtifactError, match=r"did not match anvil\.results\.v1"):
        load_results(run_dir)


def test_validate_run_manifest_rejects_paths_outside_run_dir(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside artifact", encoding="utf-8")
    digest = sha256(outside.read_bytes()).hexdigest()
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "anvil.run_manifest.v1",
                "run_id": "run_test",
                "generated_at": "2026-05-01T20:00:02Z",
                "files": [
                    {
                        "path": "../outside.txt",
                        "sha256": digest,
                        "size_bytes": outside.stat().st_size,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RunManifestError, match=r"manifest path escapes run directory"):
        validate_run_manifest(run_dir)


def test_validate_run_manifest_rejects_duplicate_file_entries(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    report = run_dir / "report.md"
    report.write_text("# Report\n", encoding="utf-8")
    digest = sha256(report.read_bytes()).hexdigest()
    file_payload = {
        "path": "report.md",
        "sha256": digest,
        "size_bytes": report.stat().st_size,
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "anvil.run_manifest.v1",
                "run_id": "run_test",
                "generated_at": "2026-05-01T20:00:02Z",
                "files": [file_payload, file_payload],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RunManifestError, match=r"duplicate manifest file entry: report\.md"):
        validate_run_manifest(run_dir)


def test_validate_run_manifest_rejects_omitted_core_artifact_entries(tmp_path) -> None:
    run_dir = tmp_path / "run_test"
    traces_dir = run_dir / "traces"
    traces_dir.mkdir(parents=True)
    report = run_dir / "report.md"
    results = run_dir / "results.json"
    trace = traces_dir / "trace.json"
    report.write_text("# Report\n", encoding="utf-8")
    results.write_text('{"ok":true}\n', encoding="utf-8")
    trace.write_text('{"schema_version":"anvil.trace.v1"}\n', encoding="utf-8")
    manifest_files = [
        {
            "path": path.relative_to(run_dir).as_posix(),
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        }
        for path in [report, results]
    ]
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "anvil.run_manifest.v1",
                "run_id": "run_test",
                "generated_at": "2026-05-01T20:00:02Z",
                "files": manifest_files,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        RunManifestError,
        match=r"manifest missing artifact entry: traces/trace\.json",
    ):
        validate_run_manifest(run_dir)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("path", ""),
        ("sha256", "not-a-sha256"),
        ("sha256", "A" * 64),
        ("size_bytes", -1),
    ],
)
def test_run_manifest_file_payload_rejects_invalid_integrity_fields(field, value) -> None:
    file_payload = {
        "path": "report.md",
        "sha256": "a" * 64,
        "size_bytes": 123,
    }
    file_payload[field] = value

    with pytest.raises(ValidationError):
        RunManifestPayload.model_validate(
            {
                "schema_version": "anvil.run_manifest.v1",
                "run_id": "run_test",
                "generated_at": "2026-05-01T20:00:02Z",
                "files": [file_payload],
            }
        )
