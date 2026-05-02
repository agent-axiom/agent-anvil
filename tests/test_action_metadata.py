from __future__ import annotations

from pathlib import Path

import yaml


def test_composite_action_exposes_agent_anvil_inputs() -> None:
    action = yaml.safe_load(Path("action.yml").read_text(encoding="utf-8"))

    assert action["name"] == "Agent Anvil"
    assert action["runs"]["using"] == "composite"
    assert set(action["inputs"]) >= {
        "scenario",
        "runs-dir",
        "offline",
        "agent-mode",
        "trials",
        "expected-exit-code",
        "github-summary",
    }


def test_agent_anvil_workflow_uses_local_composite_action() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/agent-anvil.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["demo-eval"]["steps"]

    assert any(step.get("uses") == "./" for step in steps)
    assert any(
        step.get("with", {}).get("expected-exit-code") == "1"
        for step in steps
        if step.get("uses") == "./"
    )
