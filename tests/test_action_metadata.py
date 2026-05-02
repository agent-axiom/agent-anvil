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
        "uv-cache",
    }
    setup_uv = action["runs"]["steps"][0]
    assert setup_uv["uses"] == "astral-sh/setup-uv@v8.1.0"
    assert setup_uv["with"]["enable-cache"] == "${{ inputs.uv-cache }}"


def test_agent_anvil_workflow_uses_local_composite_action() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/agent-anvil.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["demo-eval"]["steps"]

    assert any(step.get("uses") == "./" for step in steps)
    assert any(
        step.get("with", {}).get("expected-exit-code") == "1"
        for step in steps
        if step.get("uses") == "./"
    )


def test_workflows_use_node24_artifact_upload_action() -> None:
    workflow_paths = [
        Path(".github/workflows/ci.yml"),
        Path(".github/workflows/agent-anvil.yml"),
        Path(".github/workflows/openai-demo.yml"),
    ]

    for workflow_path in workflow_paths:
        workflow_text = workflow_path.read_text(encoding="utf-8")
        assert "actions/upload-artifact@v5.0.0" not in workflow_text
        assert "actions/upload-artifact@v7.0.1" in workflow_text


def test_env_file_is_ignored_but_example_is_tracked() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in gitignore
    assert "!.env.example" in gitignore
    assert Path(".env.example").exists()


def test_openai_demo_workflow_is_manual_and_uses_secret() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/openai-demo.yml").read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True))

    assert "workflow_dispatch" in triggers
    assert "push" not in triggers
    job = workflow["jobs"]["openai-demo"]
    assert job["env"]["OPENAI_API_KEY"] == "${{ secrets.OPENAI_API_KEY }}"
    assert job["env"]["ANVIL_OPENAI_MODEL"] == "gpt-5.4-mini"
    steps = job["steps"]
    assert any(step.get("name") == "Require OpenAI API key" for step in steps)
    assert any(step.get("uses") == "./" for step in steps)
    assert any(step.get("uses") == "actions/upload-artifact@v7.0.1" for step in steps)
