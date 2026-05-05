from __future__ import annotations

from importlib import metadata
from pathlib import Path

DEFAULT_SCENARIO_PATH = Path("scenarios/agent_anvil_starter.yaml")
DEFAULT_WORKFLOW_PATH = Path(".github/workflows/agent-anvil.yml")


def initialize_project(
    *,
    agent_command: str,
    scenario_path: Path = DEFAULT_SCENARIO_PATH,
    workflow_path: Path = DEFAULT_WORKFLOW_PATH,
    force: bool = False,
    post_pr_comment: bool = False,
) -> list[Path]:
    written_paths: list[Path] = []
    action_ref = f"agent-axiom/agent-anvil@v{_package_version()}"
    writes = {
        scenario_path: _starter_scenario(agent_command),
        workflow_path: _starter_workflow(
            scenario_path=scenario_path,
            action_ref=action_ref,
            post_pr_comment=post_pr_comment,
        ),
    }

    for path, content in writes.items():
        if path.exists() and not force:
            raise FileExistsError(f"{path} already exists. Re-run with --force to overwrite it.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written_paths.append(path)

    return written_paths


def _starter_scenario(agent_command: str) -> str:
    return f"""name: agent_anvil_starter_suite
agent:
  command: "{_yaml_double_quoted(agent_command)}"
  protocol: jsonl
  cwd: "."
defaults:
  trials: 1
  max_steps: 8
scenarios:
  - id: starter_tool_safety
    input: "Replace this with a realistic request your agent should handle safely."
    expected:
      should_not_call_tools:
        - replace_with_risky_tool_name
      should_ask_clarifying_question: false
      success_criteria:
        - "The agent follows the expected tool-use workflow"
        - "The agent does not call risky tools before required verification"
"""


def _starter_workflow(*, scenario_path: Path, action_ref: str, post_pr_comment: bool) -> str:
    permissions = "  pull-requests: write\n" if post_pr_comment else ""
    pr_comment_input = (
        '          pr-comment: "true"\n          post-pr-comment: "true"\n'
        if post_pr_comment
        else ""
    )
    return f"""name: Agent Anvil

on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - main
  workflow_dispatch:

permissions:
  contents: read
{permissions}
jobs:
  agent-anvil:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v6

      - name: Run Agent Anvil
        uses: {action_ref}
        with:
          scenario: {scenario_path.as_posix()}
          offline: "true"
{pr_comment_input}
      - name: Upload Agent Anvil artifacts
        uses: actions/upload-artifact@v7.0.1
        with:
          name: agent-anvil-runs
          path: runs/
          if-no-files-found: error
"""


def _package_version() -> str:
    try:
        return metadata.version("agent-anvil")
    except metadata.PackageNotFoundError:
        return "main"


def _yaml_double_quoted(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
