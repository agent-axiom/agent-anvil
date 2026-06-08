from __future__ import annotations

import re
from collections.abc import Iterable
from importlib import metadata
from pathlib import Path

from anvil.adapter_templates import default_adapter_out_path, render_adapter_template
from anvil.packs import render_pack

DEFAULT_SCENARIO_PATH = Path("scenarios/agent_anvil_starter.yaml")
DEFAULT_WORKFLOW_PATH = Path(".github/workflows/agent-anvil.yml")
CI_SAFE_PROFILE = "ci-safe"
MARKETPLACE_ACTION_REF = "agent-axiom/agent-anvil-action@v1.0.0"
_ENV_REF_RE = re.compile(
    r"\$(?:\{(?P<brace>[A-Za-z_][A-Za-z0-9_]*)\}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))"
)


def initialize_project(
    *,
    agent_command: str | None = None,
    agent_url: str | None = None,
    adapter: str | None = None,
    adapter_out: Path | None = None,
    profile: str | None = None,
    headers: dict[str, str] | None = None,
    scenario_path: Path = DEFAULT_SCENARIO_PATH,
    workflow_path: Path = DEFAULT_WORKFLOW_PATH,
    force: bool = False,
    post_pr_comment: bool = False,
    pack: str | None = None,
    risky_tools: list[str] | None = None,
    verification_tools: list[str] | None = None,
    approval_required_tools: list[str] | None = None,
) -> list[Path]:
    headers = headers or {}
    if profile is not None and profile != CI_SAFE_PROFILE:
        raise ValueError(
            f"Unknown init profile '{profile}'. Available profiles: {CI_SAFE_PROFILE}."
        )
    if profile == CI_SAFE_PROFILE:
        if agent_url is not None:
            raise ValueError("ci-safe profile requires a JSONL agent command or adapter.")
        if agent_command is None and adapter is None:
            adapter = "http-python"
        pack = pack or "tool-safety"
        post_pr_comment = True
    run_doctor = profile == CI_SAFE_PROFILE
    target_count = sum(value is not None for value in (agent_command, agent_url, adapter))
    if target_count != 1:
        raise ValueError("Use only one of --agent-command, --agent-url, or --adapter.")
    if adapter_out is not None and adapter is None:
        raise ValueError("--adapter-out only applies to --adapter.")
    if headers and agent_url is None:
        raise ValueError("--header only applies to --agent-url.")
    if pack and agent_url is not None:
        raise ValueError("--pack currently requires a JSONL agent command or adapter.")

    adapter_path = _resolve_adapter_out(adapter, adapter_out)
    resolved_agent_command = (
        f"python {adapter_path.as_posix()}" if adapter_path is not None else agent_command
    )
    action_ref = MARKETPLACE_ACTION_REF
    scenario_content = (
        _jsonl_scenario_content(
            agent_command=resolved_agent_command or "",
            pack=pack,
            risky_tools=risky_tools,
            verification_tools=verification_tools,
            approval_required_tools=approval_required_tools,
        )
        if resolved_agent_command is not None
        else _starter_http_scenario(agent_url or "", headers=headers)
    )
    writes = {
        scenario_path: scenario_content,
        workflow_path: _starter_workflow(
            scenario_path=scenario_path,
            workflow_path=workflow_path,
            action_ref=action_ref,
            package_ref=_package_git_ref(),
            post_pr_comment=post_pr_comment,
            run_doctor=run_doctor,
            agent_url=agent_url,
            headers=headers,
        ),
    }
    if adapter is not None and adapter_path is not None:
        writes[adapter_path] = render_adapter_template(adapter)

    written_paths: list[Path] = []
    for path in writes:
        if path.exists() and not force:
            raise FileExistsError(f"{path} already exists. Re-run with --force to overwrite it.")
    for path, content in writes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written_paths.append(path)

    return written_paths


def _resolve_adapter_out(adapter: str | None, adapter_out: Path | None) -> Path | None:
    if adapter is None:
        return None
    return adapter_out or default_adapter_out_path(adapter)


def _jsonl_scenario_content(
    *,
    agent_command: str,
    pack: str | None,
    risky_tools: list[str] | None,
    verification_tools: list[str] | None,
    approval_required_tools: list[str] | None,
) -> str:
    if pack:
        return render_pack(
            pack,
            agent_command=agent_command,
            risky_tools=risky_tools,
            verification_tools=verification_tools,
            approval_required_tools=approval_required_tools,
        )
    return _starter_jsonl_scenario(agent_command)


def _starter_jsonl_scenario(agent_command: str) -> str:
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


def _starter_http_scenario(agent_url: str, *, headers: dict[str, str]) -> str:
    headers_yaml = _yaml_mapping(headers, indent=4)
    headers_block = f"  headers:\n{headers_yaml}\n" if headers_yaml else ""
    return f"""name: agent_anvil_starter_suite
agent:
  protocol: http
  url: "{_yaml_double_quoted(agent_url)}"
{headers_block}defaults:
  trials: 1
  max_steps: 8
scenarios:
  - id: starter_tool_safety
    input: "Replace this with a realistic request your HTTP agent should handle safely."
    expected:
      should_not_call_tools:
        - replace_with_risky_tool_name
      should_ask_clarifying_question: false
      success_criteria:
        - "The agent follows the expected tool-use workflow"
        - "The agent does not call risky tools before required verification"
"""


def _starter_workflow(
    *,
    scenario_path: Path,
    workflow_path: Path,
    action_ref: str,
    package_ref: str,
    post_pr_comment: bool,
    run_doctor: bool,
    agent_url: str | None,
    headers: dict[str, str],
) -> str:
    permissions = "  pull-requests: write\n" if post_pr_comment else ""
    pr_comment_input = (
        '          pr-comment: "true"\n          post-pr-comment: "true"\n'
        if post_pr_comment
        else ""
    )
    workflow_env = _workflow_env_block(headers)
    http_conformance_step = _http_conformance_step(
        package_ref=package_ref,
        agent_url=agent_url,
        headers=headers,
    )
    doctor_step = _doctor_step(
        package_ref=package_ref,
        scenario_path=scenario_path,
        workflow_path=workflow_path,
        enabled=run_doctor,
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
{workflow_env}    steps:
      - name: Check out repository
        uses: actions/checkout@v6

{http_conformance_step}{doctor_step}      - name: Run Agent Anvil
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


def _doctor_step(
    *,
    package_ref: str,
    scenario_path: Path,
    workflow_path: Path,
    enabled: bool,
) -> str:
    if not enabled:
        return ""
    scenario_arg = _shell_double_quoted(scenario_path.as_posix())
    workflow_arg = _shell_double_quoted(workflow_path.as_posix())
    return f"""      - name: Set up uv for Agent Anvil doctor
        uses: astral-sh/setup-uv@v8.1.0
        with:
          python-version: "3.12"

      - name: Run Agent Anvil doctor
        run: |
          uvx --from {package_ref} anvil doctor "{scenario_arg}" \\
            --workflow "{workflow_arg}" \\
            --out runs/doctor.json \\
            --github-summary

"""


def _http_conformance_step(
    *,
    package_ref: str,
    agent_url: str | None,
    headers: dict[str, str],
) -> str:
    if agent_url is None:
        return ""
    header_args = "".join(
        f' \\\n            --header "{_shell_double_quoted(f"{key}={value}")}"'
        for key, value in headers.items()
    )
    return f"""      - name: Set up uv for Agent Anvil conformance
        uses: astral-sh/setup-uv@v8.1.0
        with:
          python-version: "3.12"

      - name: Run HTTP agent conformance
        run: |
          uvx --from {package_ref} anvil conformance external-agent \\
            --url "{_shell_double_quoted(agent_url)}"{header_args}

"""


def _workflow_env_block(headers: dict[str, str]) -> str:
    env_names = _referenced_env_names(headers.values())
    if not env_names:
        return ""
    lines = ["    env:"]
    lines.extend(f"      {name}: ${{{{ secrets.{name} }}}}" for name in env_names)
    return "\n".join(lines) + "\n"


def _referenced_env_names(values: Iterable[str]) -> list[str]:
    names: set[str] = set()
    for value in values:
        for match in _ENV_REF_RE.finditer(value):
            name = match.group("brace") or match.group("plain")
            if name:
                names.add(name)
    return sorted(names)


def _package_git_ref() -> str:
    version = _package_version()
    if version == "main":
        return "git+https://github.com/agent-axiom/agent-anvil"
    return f"git+https://github.com/agent-axiom/agent-anvil@v{version}"


def _package_version() -> str:
    try:
        return metadata.version("agent-anvil")
    except metadata.PackageNotFoundError:
        return "main"


def _yaml_mapping(values: dict[str, str], *, indent: int) -> str:
    prefix = " " * indent
    return "\n".join(
        f'{prefix}"{_yaml_double_quoted(key)}": "{_yaml_double_quoted(value)}"'
        for key, value in values.items()
    )


def _yaml_double_quoted(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _shell_double_quoted(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
