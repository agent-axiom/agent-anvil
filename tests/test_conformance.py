from __future__ import annotations

import json
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from anvil.cli import app


class _ConformanceHttpServer:
    def __init__(self, response_payload: dict[str, Any], status_code: int = 200) -> None:
        self.requests: list[dict[str, Any]] = []
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                requests.append(
                    {
                        "headers": dict(self.headers),
                        "payload": json.loads(body.decode()),
                    }
                )
                response_body = json.dumps(response_payload).encode()
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                del format, args

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}/anvil"

    def __enter__(self) -> _ConformanceHttpServer:
        self.thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


@pytest.fixture
def http_conformance_agent() -> Iterator[_ConformanceHttpServer]:
    with _ConformanceHttpServer(
        {
            "events": [
                {
                    "type": "model_call",
                    "model": "http-conformance-agent",
                    "output_text": "Conformance ok.",
                    "tool_calls": [],
                },
                {"type": "final_output", "text": "http agent ok"},
            ]
        }
    ) as server:
        yield server


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


def test_external_agent_conformance_rejects_malformed_header(
    http_conformance_agent: _ConformanceHttpServer,
) -> None:
    result = CliRunner().invoke(
        app,
        [
            "conformance",
            "external-agent",
            "--url",
            http_conformance_agent.url,
            "--header",
            "NOT_KEY_VALUE",
        ],
    )

    assert result.exit_code == 2
    assert "--header must use KEY=VALUE" in result.output


def test_external_agent_conformance_passes_for_http_endpoint(
    http_conformance_agent: _ConformanceHttpServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANVIL_CONFORMANCE_TOKEN", "token-123")
    report_path = tmp_path / "http-conformance.md"
    result = CliRunner().invoke(
        app,
        [
            "conformance",
            "external-agent",
            "--url",
            http_conformance_agent.url,
            "--header",
            "Authorization=Bearer $ANVIL_CONFORMANCE_TOKEN",
            "--out",
            str(report_path),
        ],
    )

    assert result.exit_code == 0
    assert "External agent conformance: PASS" in result.output
    assert http_conformance_agent.requests[0]["payload"]["scenario_id"] == (
        "external_agent_conformance"
    )
    assert http_conformance_agent.requests[0]["headers"]["Authorization"] == "Bearer token-123"
    report = report_path.read_text(encoding="utf-8")
    assert "http agent ok" in report


def test_external_agent_conformance_fails_for_http_status() -> None:
    with _ConformanceHttpServer({"error": "bad agent"}, status_code=500) as server:
        result = CliRunner().invoke(
            app,
            [
                "conformance",
                "external-agent",
                "--url",
                server.url,
            ],
        )

    assert result.exit_code == 1
    assert "External agent conformance: FAIL" in result.output
    assert "http_status" in result.output


def test_external_agent_conformance_rejects_ambiguous_agent_targets(
    http_conformance_agent: _ConformanceHttpServer,
) -> None:
    result = CliRunner().invoke(
        app,
        [
            "conformance",
            "external-agent",
            "--agent-command",
            f"{sys.executable} fixtures/conformance/pass_agent.py",
            "--url",
            http_conformance_agent.url,
        ],
    )

    assert result.exit_code == 2
    assert "Use either --agent-command or --url" in result.output
