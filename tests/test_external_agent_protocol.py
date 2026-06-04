from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from anvil.grading import HeuristicSemanticGrader
from anvil.runner import run_suite


def test_run_suite_accepts_jsonl_external_agent(tmp_path: Path) -> None:
    agent_script = tmp_path / "jsonl_agent.py"
    agent_script.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import json",
                "import sys",
                "payload = json.loads(sys.stdin.read())",
                "print(json.dumps({",
                "    'type': 'model_call',",
                "    'model': 'external-demo',",
                "    'input': payload['input'],",
                "    'output_text': 'I will look up the order.',",
                "    'tool_calls': [",
                "        {'name': 'lookup_order', 'arguments': {'order_id': 'ORD-123'}},",
                "    ],",
                "}))",
                "print(json.dumps({",
                "    'type': 'tool_call',",
                "    'tool_name': 'lookup_order',",
                "    'arguments': {'order_id': 'ORD-123'},",
                "    'result': {'status': 'found'},",
                "}))",
                "print(json.dumps({'type': 'final_output', 'text': 'Order verified.'}))",
            ]
        ),
        encoding="utf-8",
    )
    scenario_file = tmp_path / "external.yaml"
    scenario_file.write_text(
        f"""
name: external_agent_suite
agent:
  command: "{sys.executable} {agent_script}"
  protocol: jsonl
defaults:
  trials: 1
  max_steps: 8
scenarios:
  - id: external_order_lookup
    input: "Please check ORD-123."
    expected:
      should_call_tools:
        - lookup_order
      success_criteria:
        - "Looks up the order"
""",
        encoding="utf-8",
    )

    result = run_suite(
        scenario_file,
        runs_dir=tmp_path / "runs",
        semantic_grader=HeuristicSemanticGrader(),
    )

    assert result.total_trials == 1
    assert result.passed_trials == 1
    assert result.grades[0].trace_path.endswith("external_order_lookup_trial_1.json")


def test_external_agent_config_passes_cwd_and_env(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    agent_script = agent_dir / "cwd_env_agent.py"
    agent_script.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import json",
                "import os",
                "from pathlib import Path",
                "payload = json.loads(input())",
                "print(json.dumps({",
                "    'type': 'model_call',",
                "    'model': 'cwd-env-agent',",
                "    'input': payload['input'],",
                "    'output_text': Path.cwd().name + ':' + os.environ['AGENT_MODE'],",
                "    'tool_calls': [],",
                "}))",
                "print(json.dumps({'type': 'final_output', 'text': 'cwd/env ok'}))",
            ]
        ),
        encoding="utf-8",
    )
    scenario_file = tmp_path / "external.yaml"
    scenario_file.write_text(
        f"""
name: external_agent_suite
agent:
  command: "{sys.executable} cwd_env_agent.py"
  protocol: jsonl
  cwd: "{agent_dir}"
  env:
    AGENT_MODE: test
defaults:
  trials: 1
  max_steps: 8
scenarios:
  - id: cwd_env
    input: "hello"
    expected:
      success_criteria:
        - "Agent receives cwd and env"
""",
        encoding="utf-8",
    )

    result = run_suite(
        scenario_file,
        runs_dir=tmp_path / "runs",
        semantic_grader=HeuristicSemanticGrader(),
    )

    trace_payload = json.loads(Path(result.grades[0].trace_path).read_text(encoding="utf-8"))
    assert result.passed_trials == 1
    assert trace_payload["steps"][0]["output_text"] == "agent:test"


def test_bundled_external_jsonl_scenario_runs(tmp_path: Path) -> None:
    result = run_suite(
        "scenarios/external_jsonl_agent.yaml",
        runs_dir=tmp_path / "runs",
        semantic_grader=HeuristicSemanticGrader(),
    )

    assert result.total_trials == 1
    assert result.passed_trials == 1


def test_external_agent_malformed_jsonl_becomes_failed_trace(tmp_path: Path) -> None:
    agent_script = tmp_path / "bad_jsonl_agent.py"
    agent_script.write_text("print('not json')\n", encoding="utf-8")
    scenario_file = tmp_path / "external.yaml"
    scenario_file.write_text(
        f"""
name: external_agent_suite
agent:
  command: "{sys.executable} {agent_script}"
  protocol: jsonl
defaults:
  trials: 1
  max_steps: 8
scenarios:
  - id: malformed_jsonl
    input: "hello"
""",
        encoding="utf-8",
    )

    result = run_suite(
        scenario_file,
        runs_dir=tmp_path / "runs",
        semantic_grader=HeuristicSemanticGrader(),
    )

    trace_payload = json.loads(Path(result.grades[0].trace_path).read_text(encoding="utf-8"))
    assert result.passed_trials == 0
    assert trace_payload["status"] == "failed"
    assert trace_payload["steps"][0]["type"] == "agent_protocol_error"
    assert "Agent protocol error" in trace_payload["final_output"]


def test_external_agent_invalid_event_schema_becomes_failed_trace(tmp_path: Path) -> None:
    agent_script = tmp_path / "bad_event_agent.py"
    agent_script.write_text(
        "\n".join(
            [
                "import json",
                "print(json.dumps({'type': 'tool_call'}))",
                "print(json.dumps({'type': 'final_output', 'text': 'done'}))",
            ]
        ),
        encoding="utf-8",
    )
    scenario_file = tmp_path / "external.yaml"
    scenario_file.write_text(
        f"""
name: external_agent_suite
agent:
  command: "{sys.executable} {agent_script}"
  protocol: jsonl
defaults:
  trials: 1
  max_steps: 8
scenarios:
  - id: invalid_event
    input: "hello"
""",
        encoding="utf-8",
    )

    result = run_suite(
        scenario_file,
        runs_dir=tmp_path / "runs",
        semantic_grader=HeuristicSemanticGrader(),
    )

    trace_payload = json.loads(Path(result.grades[0].trace_path).read_text(encoding="utf-8"))
    assert result.passed_trials == 0
    assert trace_payload["status"] == "failed"
    assert trace_payload["steps"][0]["type"] == "agent_protocol_error"
    assert (
        "tool_call event on line 1 missing required fields: arguments, result, tool_name"
        in (trace_payload["final_output"])
    )


def test_external_agent_timeout_becomes_failed_trace(tmp_path: Path) -> None:
    agent_script = tmp_path / "slow_agent.py"
    agent_script.write_text(
        "\n".join(["import time", "time.sleep(2)", 'print(\'{"type":"final_output"}\')']),
        encoding="utf-8",
    )
    scenario_file = tmp_path / "external.yaml"
    scenario_file.write_text(
        f"""
name: external_agent_suite
agent:
  command: "{sys.executable} {agent_script}"
  protocol: jsonl
  timeout_seconds: 1
defaults:
  trials: 1
  max_steps: 8
scenarios:
  - id: timeout_agent
    input: "hello"
""",
        encoding="utf-8",
    )

    result = run_suite(
        scenario_file,
        runs_dir=tmp_path / "runs",
        semantic_grader=HeuristicSemanticGrader(),
    )

    trace_payload = json.loads(Path(result.grades[0].trace_path).read_text(encoding="utf-8"))
    assert result.passed_trials == 0
    assert trace_payload["status"] == "failed"
    assert trace_payload["steps"][0]["type"] == "agent_protocol_error"
    assert "timed out" in trace_payload["final_output"]


def test_run_suite_accepts_http_agent_endpoint(tmp_path: Path) -> None:
    requests: list[dict[str, Any]] = []

    def handler(payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        requests.append({"payload": payload, "headers": headers})
        return {
            "steps": [
                {
                    "type": "model_call",
                    "model": "http-demo",
                    "input": payload["input"],
                    "output_text": "I will look up the order.",
                    "tool_calls": [{"name": "lookup_order", "arguments": {"order_id": "ORD-123"}}],
                },
                {
                    "type": "tool_call",
                    "tool_name": "lookup_order",
                    "arguments": {"order_id": "ORD-123"},
                    "result": {"status": "found"},
                },
            ],
            "final_output": "Order verified.",
        }

    with _http_agent_server(handler) as endpoint:
        scenario_file = tmp_path / "http-agent.yaml"
        scenario_file.write_text(
            f"""
name: http_agent_suite
agent:
  protocol: http
  url: "{endpoint}"
  headers:
    X-Agent-Anvil: test
defaults:
  trials: 1
  max_steps: 8
scenarios:
  - id: http_order_lookup
    input: "Please check ORD-123."
    expected:
      should_call_tools:
        - lookup_order
""",
            encoding="utf-8",
        )

        result = run_suite(
            scenario_file,
            runs_dir=tmp_path / "runs",
            semantic_grader=HeuristicSemanticGrader(),
        )

    trace_payload = json.loads(Path(result.grades[0].trace_path).read_text(encoding="utf-8"))
    assert result.passed_trials == 1
    assert requests[0]["payload"]["scenario_id"] == "http_order_lookup"
    assert requests[0]["payload"]["input"] == "Please check ORD-123."
    assert requests[0]["headers"]["X-Agent-Anvil"] == "test"
    assert trace_payload["status"] == "completed"
    assert trace_payload["steps"][1]["tool_name"] == "lookup_order"
    assert trace_payload["final_output"] == "Order verified."


def test_http_agent_expands_environment_headers(tmp_path: Path, monkeypatch: Any) -> None:
    requests: list[dict[str, Any]] = []
    monkeypatch.setenv("ANVIL_HTTP_AGENT_TOKEN", "secret-test-token")

    def handler(payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        requests.append({"payload": payload, "headers": headers})
        return {"events": [{"type": "final_output", "text": "ok"}]}

    with _http_agent_server(handler) as endpoint:
        scenario_file = tmp_path / "http-headers.yaml"
        scenario_file.write_text(
            f"""
name: http_headers_suite
agent:
  protocol: http
  url: "{endpoint}"
  headers:
    Authorization: "Bearer $ANVIL_HTTP_AGENT_TOKEN"
defaults:
  trials: 1
scenarios:
  - id: http_headers
    input: "hello"
""",
            encoding="utf-8",
        )

        result = run_suite(
            scenario_file,
            runs_dir=tmp_path / "runs",
            semantic_grader=HeuristicSemanticGrader(),
        )

    assert result.passed_trials == 1
    assert requests[0]["headers"]["Authorization"] == "Bearer secret-test-token"


def test_http_agent_endpoint_accepts_event_response(tmp_path: Path) -> None:
    def handler(payload: dict[str, Any], _headers: dict[str, str]) -> dict[str, Any]:
        return {
            "events": [
                {
                    "type": "model_call",
                    "model": "http-events-demo",
                    "input": payload["input"],
                    "output_text": "done",
                    "tool_calls": [],
                },
                {"type": "final_output", "text": "Done."},
            ]
        }

    with _http_agent_server(handler) as endpoint:
        scenario_file = tmp_path / "http-events.yaml"
        scenario_file.write_text(
            f"""
name: http_events_suite
agent:
  protocol: http
  url: "{endpoint}"
defaults:
  trials: 1
scenarios:
  - id: http_events
    input: "hello"
""",
            encoding="utf-8",
        )

        result = run_suite(
            scenario_file,
            runs_dir=tmp_path / "runs",
            semantic_grader=HeuristicSemanticGrader(),
        )

    trace_payload = json.loads(Path(result.grades[0].trace_path).read_text(encoding="utf-8"))
    assert result.passed_trials == 1
    assert trace_payload["steps"][0]["model"] == "http-events-demo"
    assert trace_payload["final_output"] == "Done."


def test_http_agent_non_2xx_becomes_failed_trace(tmp_path: Path) -> None:
    def handler(_payload: dict[str, Any], _headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
        return 503, {"error": "agent unavailable"}

    with _http_agent_server(handler) as endpoint:
        scenario_file = tmp_path / "http-failure.yaml"
        scenario_file.write_text(
            f"""
name: http_failure_suite
agent:
  protocol: http
  url: "{endpoint}"
defaults:
  trials: 1
scenarios:
  - id: http_failure
    input: "hello"
""",
            encoding="utf-8",
        )

        result = run_suite(
            scenario_file,
            runs_dir=tmp_path / "runs",
            semantic_grader=HeuristicSemanticGrader(),
        )

    trace_payload = json.loads(Path(result.grades[0].trace_path).read_text(encoding="utf-8"))
    assert result.passed_trials == 0
    assert trace_payload["status"] == "failed"
    assert trace_payload["steps"][0]["type"] == "agent_protocol_error"
    assert trace_payload["steps"][0]["error_type"] == "http_status"
    assert "503" in trace_payload["final_output"]


class _HttpAgentServer:
    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> str:
        user_handler = self.handler

        class RequestHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                content_length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(content_length))
                result = user_handler(payload, dict(self.headers))
                status_code = 200
                response_payload = result
                if isinstance(result, tuple):
                    status_code, response_payload = result
                body = json.dumps(response_payload).encode()
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                _ = (format, args)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host = self.server.server_address[0]
        port = self.server.server_address[1]
        return f"http://{host}:{port}/anvil"

    def __exit__(self, *_exc: object) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)


def _http_agent_server(handler: Any) -> _HttpAgentServer:
    return _HttpAgentServer(handler)
