from __future__ import annotations

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
