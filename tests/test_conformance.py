from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

from anvil.cli import app


def test_external_agent_conformance_passes_for_valid_jsonl_agent(tmp_path: Path) -> None:
    report_path = tmp_path / "conformance.md"
    result = CliRunner().invoke(
        app,
        [
            "conformance",
            "external-agent",
            "--agent-command",
            f"{sys.executable} fixtures/conformance/pass_agent.py",
            "--out",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert "External agent conformance: PASS" in result.output
    assert "Wrote conformance report:" in result.output
    report = report_path.read_text(encoding="utf-8")
    assert "# Agent Anvil External Agent Conformance" in report
    assert "| process_completed | PASS |" in report
    assert "external agent ok" in report


def test_external_agent_conformance_supports_cwd_and_env(tmp_path: Path) -> None:
    report_path = tmp_path / "conformance.md"
    result = CliRunner().invoke(
        app,
        [
            "conformance",
            "external-agent",
            "--agent-command",
            f"{sys.executable} pass_agent.py",
            "--cwd",
            "fixtures/conformance",
            "--env",
            "ANVIL_CONFORMANCE_MARKER=test-env",
            "--out",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert "External agent conformance: PASS" in result.output
    report = report_path.read_text(encoding="utf-8")
    assert "cwd=conformance" in report
    assert "env=test-env" in report


def test_external_agent_conformance_fails_for_malformed_jsonl() -> None:
    result = CliRunner().invoke(
        app,
        [
            "conformance",
            "external-agent",
            "--agent-command",
            f"{sys.executable} fixtures/conformance/malformed_agent.py",
        ],
    )

    assert result.exit_code == 1
    assert "External agent conformance: FAIL" in result.output
    assert "agent_protocol_error" in result.output
    assert "malformed_jsonl" in result.output


def test_external_agent_conformance_fails_without_final_output() -> None:
    result = CliRunner().invoke(
        app,
        [
            "conformance",
            "external-agent",
            "--agent-command",
            f"{sys.executable} fixtures/conformance/missing_final_output_agent.py",
        ],
    )

    assert result.exit_code == 1
    assert "External agent conformance: FAIL" in result.output
    assert "final_output_present" in result.output


def test_external_agent_conformance_rejects_malformed_env() -> None:
    result = CliRunner().invoke(
        app,
        [
            "conformance",
            "external-agent",
            "--agent-command",
            f"{sys.executable} fixtures/conformance/pass_agent.py",
            "--env",
            "NOT_KEY_VALUE",
        ],
    )

    assert result.exit_code == 2
    assert "--env must use KEY=VALUE" in result.output
