from __future__ import annotations

import json
import sys
from pathlib import Path

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
    assert "tool_call event on line 1 missing required fields: arguments, result, tool_name" in (
        trace_payload["final_output"]
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
