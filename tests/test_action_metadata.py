from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path

import yaml


def test_project_metadata_supports_python_312_plus() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["requires-python"] == ">=3.12"
    assert pyproject["tool"]["ruff"]["target-version"] == "py312"
    assert pyproject["tool"]["ty"]["environment"]["python-version"] == "3.12"
    assert Path(".python-version").read_text(encoding="utf-8").strip() == "3.12"


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
        "pr-comment",
        "post-pr-comment",
        "pr-comment-path",
        "compare-baseline",
        "compare-path",
        "uv-cache",
    }
    assert action["inputs"]["python-version"]["default"] == "3.12"
    setup_uv = action["runs"]["steps"][0]
    assert setup_uv["uses"] == "astral-sh/setup-uv@v8.1.0"
    assert setup_uv["with"]["enable-cache"] == "${{ inputs.uv-cache }}"
    assert setup_uv["with"]["python-version"] == "${{ inputs.python-version }}"


def test_composite_action_fails_when_expected_failure_passes(tmp_path: Path) -> None:
    action = yaml.safe_load(Path("action.yml").read_text(encoding="utf-8"))
    run_step = next(step for step in action["runs"]["steps"] if step["name"] == "Run Agent Anvil")
    script = (
        run_step["run"]
        .replace("${{ inputs.scenario }}", "scenario.yaml")
        .replace("${{ inputs.runs-dir }}", "runs/action-test")
        .replace("${{ inputs.offline }}", "true")
        .replace("${{ inputs.agent-mode }}", "")
        .replace("${{ inputs.trials }}", "")
        .replace("${{ inputs.expected-exit-code }}", "1")
        .replace("${{ inputs.github-summary }}", "false")
        .replace("${{ inputs.pr-comment }}", "false")
        .replace("${{ inputs.post-pr-comment }}", "false")
        .replace("${{ inputs.pr-comment-path }}", "agent-anvil-pr-comment.md")
        .replace("${{ inputs.compare-baseline }}", "")
        .replace("${{ inputs.compare-path }}", "agent-anvil-compare.json")
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_uv.chmod(0o755)

    completed = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_ACTION_PATH": str(tmp_path),
            "GITHUB_WORKSPACE": str(tmp_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "Agent Anvil exited with 0, expected 1." in completed.stdout


def test_ci_runs_against_python_312_and_314() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["test"]

    assert job["strategy"]["fail-fast"] is False
    assert job["strategy"]["matrix"]["python-version"] == ["3.12", "3.14"]

    setup_python = next(
        step for step in job["steps"] if step.get("uses") == "actions/setup-python@v6"
    )
    assert setup_python["with"]["python-version"] == "${{ matrix.python-version }}"

    setup_uv = next(
        step for step in job["steps"] if step.get("uses") == "astral-sh/setup-uv@v8.1.0"
    )
    assert setup_uv["with"]["python-version"] == "${{ matrix.python-version }}"

    upload = next(
        step for step in job["steps"] if step.get("uses") == "actions/upload-artifact@v7.0.1"
    )
    assert upload["with"]["name"] == "coverage-xml-${{ matrix.python-version }}"
    assert upload["continue-on-error"] is True


MARKETPLACE_ACTION_REF = "agent-axiom/agent-anvil-action@v1.0.39"


def test_agent_anvil_workflow_uses_marketplace_action() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/agent-anvil.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["demo-eval"]["steps"]

    assert any(step.get("uses") == MARKETPLACE_ACTION_REF for step in steps)
    assert any(
        step.get("with", {}).get("expected-exit-code") == "1"
        for step in steps
        if step.get("uses") == MARKETPLACE_ACTION_REF
    )


def test_agent_anvil_workflow_runs_mcp_harden_demo() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/agent-anvil.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["demo-eval"]["steps"]
    harden_step = next(step for step in steps if step.get("name") == "Harden demo MCP server")
    upload_step = next(
        step for step in steps if step.get("uses") == "actions/upload-artifact@v7.0.1"
    )

    assert "anvil mcp harden" in harden_step["run"]
    assert "docs/examples/fake_mcp_server.py" in harden_step["run"]
    assert "--github-summary" in harden_step["run"]
    assert "reports/mcp/" in upload_step["with"]["path"]


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
    assert any(step.get("uses") == MARKETPLACE_ACTION_REF for step in steps)
    action_step = next(step for step in steps if step.get("uses") == MARKETPLACE_ACTION_REF)
    assert action_step["with"].get("expected-exit-code", "0") == "0"
    assert any(step.get("uses") == "actions/upload-artifact@v7.0.1" for step in steps)


def test_readme_action_snippet_starts_with_passing_smoke_example() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "scenario: scenarios/external_jsonl_agent.yaml" in readme
    assert 'expected-exit-code: "1"' in readme


def test_composite_action_can_generate_pr_comment_file() -> None:
    action = yaml.safe_load(Path("action.yml").read_text(encoding="utf-8"))
    run_step = next(step for step in action["runs"]["steps"] if step["name"] == "Run Agent Anvil")

    assert action["inputs"]["pr-comment"]["default"] == "false"
    assert action["inputs"]["post-pr-comment"]["default"] == "false"
    assert action["inputs"]["pr-comment-path"]["default"] == "agent-anvil-pr-comment.md"
    assert action["inputs"]["compare-baseline"]["default"] == ""
    assert action["inputs"]["compare-path"]["default"] == "agent-anvil-compare.json"
    assert 'pr_args=(pr-comment "$runs_dir/latest" --out "$comment_path")' in run_step["run"]
    assert 'anvil "${pr_args[@]}"' in run_step["run"]
    assert 'gh pr comment "$pr_number" --body-file "$comment_path"' in run_step["run"]


def test_composite_action_can_wire_compare_artifact_into_pr_comment() -> None:
    action = yaml.safe_load(Path("action.yml").read_text(encoding="utf-8"))
    run_step = next(step for step in action["runs"]["steps"] if step["name"] == "Run Agent Anvil")

    assert 'baseline_dir="${{ inputs.compare-baseline }}"' in run_step["run"]
    assert 'compare_path="${{ inputs.compare-path }}"' in run_step["run"]
    assert (
        'anvil compare "$baseline_dir" "$runs_dir/latest" --out "$compare_path"' in run_step["run"]
    )
    assert 'pr_args+=(--compare "$compare_path")' in run_step["run"]


def test_composite_action_skips_pr_comment_publish_outside_pull_request(tmp_path: Path) -> None:
    action = yaml.safe_load(Path("action.yml").read_text(encoding="utf-8"))
    run_step = next(step for step in action["runs"]["steps"] if step["name"] == "Run Agent Anvil")
    script = (
        run_step["run"]
        .replace("${{ inputs.scenario }}", "scenario.yaml")
        .replace("${{ inputs.runs-dir }}", "runs/action-test")
        .replace("${{ inputs.offline }}", "true")
        .replace("${{ inputs.agent-mode }}", "")
        .replace("${{ inputs.trials }}", "")
        .replace("${{ inputs.expected-exit-code }}", "0")
        .replace("${{ inputs.github-summary }}", "false")
        .replace("${{ inputs.pr-comment }}", "false")
        .replace("${{ inputs.post-pr-comment }}", "true")
        .replace("${{ inputs.pr-comment-path }}", "agent-anvil-pr-comment.md")
        .replace("${{ inputs.compare-baseline }}", "")
        .replace("${{ inputs.compare-path }}", "agent-anvil-compare.json")
        .replace("${{ github.event_name }}", "push")
        .replace("${{ github.event.pull_request.number }}", "")
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$*" == *"pr-comment"* ]]; then\n'
        "  while [[ $# -gt 0 ]]; do\n"
        '    if [[ "$1" == "--out" ]]; then\n'
        "      printf 'comment generated\\n' > \"$2\"\n"
        "      break\n"
        "    fi\n"
        "    shift\n"
        "  done\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)

    completed = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_ACTION_PATH": str(tmp_path),
            "GITHUB_WORKSPACE": str(tmp_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Skipping PR comment publish outside pull_request event." in completed.stdout


def test_composite_action_has_marketplace_branding() -> None:
    action = yaml.safe_load(Path("action.yml").read_text(encoding="utf-8"))

    assert action["branding"] == {"icon": "activity", "color": "purple"}


def test_readme_has_30_second_core_loop_demo() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "## 30-Second Demo" in readme
    assert "run -> trace -> check -> grade -> report -> CI" in readme
    assert "docs/submission.md" in readme


def test_mcp_and_marketplace_docs_are_linked() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")

    assert "docs/mcp.md" in readme
    assert "marketplace.md" in artifacts
    assert "MCP Tool Audit" in Path("docs/mcp.md").read_text(encoding="utf-8")
    assert "anvil mcp snapshot" in Path("docs/mcp.md").read_text(encoding="utf-8")
    assert "GitHub Marketplace" in Path("docs/marketplace.md").read_text(encoding="utf-8")


def test_mcp_harden_example_workflow_is_copy_paste_ready() -> None:
    workflow_path = Path("docs/examples/mcp-harden-workflow.yml")
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["mcp-safety-audit"]["steps"]
    harden_step = next(step for step in steps if step.get("name") == "Audit MCP tool surface")
    upload_step = next(
        step for step in steps if step.get("uses") == "actions/upload-artifact@v7.0.1"
    )

    assert "pull_request" in workflow.get("on", workflow.get(True))
    assert "anvil mcp harden" in harden_step["run"]
    assert "--command-json" in harden_step["run"]
    assert "--github-summary" in harden_step["run"]
    assert upload_step["with"]["name"] == "agent-anvil-mcp-safety-audit"
    assert "docs/examples/mcp-harden-workflow.yml" in Path("README.md").read_text(encoding="utf-8")


def test_pr_comment_workflow_is_documented_and_wired() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/agent-anvil.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["demo-eval"]["steps"]

    regression_step = next(
        step for step in steps if step.get("name") == "Run intentional refund regression demo"
    )
    assert regression_step["with"]["pr-comment"] == "true"
    assert regression_step["with"]["pr-comment-path"] == "agent-anvil-pr-comment.md"
    upload_path = next(
        step["with"]["path"]
        for step in steps
        if step.get("uses") == "actions/upload-artifact@v7.0.1"
    )
    assert "runs/" in upload_path
    assert "agent-anvil-pr-comment.md" in upload_path


def test_pr_comment_example_workflow_is_copy_paste_ready() -> None:
    workflow_path = Path("docs/examples/pr-comment-workflow.yml")
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    job = workflow["jobs"]["agent-anvil"]["steps"]

    assert workflow["permissions"] == {"contents": "read", "pull-requests": "write"}
    assert any(step.get("uses") == MARKETPLACE_ACTION_REF for step in job)
    action_step = next(step for step in job if step.get("uses", "").startswith("agent-axiom/"))
    assert action_step["with"]["post-pr-comment"] == "true"
    assert "docs/examples/pr-comment-workflow.yml" in Path("README.md").read_text(encoding="utf-8")


def test_readme_action_reference_uses_marketplace_release() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert MARKETPLACE_ACTION_REF in readme
    assert "agent-axiom/agent-anvil@v" not in readme


def test_submission_version_matches_package_version() -> None:
    submission = Path("docs/submission.md").read_text(encoding="utf-8")
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert f"Current `v{pyproject['project']['version']}`" in submission
