from __future__ import annotations

from pathlib import Path

import yaml


def test_contributing_guide_explains_scenarios_and_privacy() -> None:
    text = Path("CONTRIBUTING.md").read_text(encoding="utf-8")

    assert "Writing Scenarios" in text
    assert "Bring Your Own Agent" in text
    assert "Data Privacy" in text
    assert "uv run anvil run scenarios/external_jsonl_agent.yaml --offline" in text


def test_scenario_authoring_doc_is_linked_from_readme() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    doc = Path("docs/scenarios.md").read_text(encoding="utf-8")

    assert "docs/scenarios.md" in readme
    assert "Scenario Authoring Guide" in doc
    assert "should_not_call_tools" in doc
    assert "policies:" in doc


def test_init_doc_is_linked_from_readme() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    doc = Path("docs/init.md").read_text(encoding="utf-8")
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")

    assert "init.md" in artifacts
    assert "uv run anvil init --agent-command" in readme
    assert "--pack tool-safety" in doc
    assert "post-pr-comment" in doc
    assert "--force" in doc


def test_packs_doc_is_linked_from_readme() -> None:
    doc = Path("docs/packs.md").read_text(encoding="utf-8")
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")

    assert "packs.md" in artifacts
    assert "uv run anvil pack list" in doc
    assert "tool-safety" in doc
    assert "destructive_tools" in doc
    assert "--risky-tool" in doc
    assert "--verification-tool" in doc


def test_ingest_doc_is_linked_from_readme() -> None:
    doc = Path("docs/ingest.md").read_text(encoding="utf-8")
    cli_doc = Path("docs/cli.md").read_text(encoding="utf-8")
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")

    assert "ingest.md" in artifacts
    assert "uv run anvil ingest jsonl" in cli_doc
    assert "uv run anvil learn jsonl" in cli_doc
    assert "production failure log -> Anvil trace" in doc
    assert "anvil learn" in doc


def test_artifacts_and_cli_docs_are_linked_from_readme() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")
    cli_doc = Path("docs/cli.md").read_text(encoding="utf-8")

    assert "docs/artifacts.md" in readme
    assert "docs/cli.md" in readme
    assert "OpenAI-graded regression report" in artifacts
    assert "MCP Hardening" in artifacts
    assert "uv run anvil compare runs/baseline runs/latest" in cli_doc
    assert "uv run anvil mcp harden" in cli_doc


def test_judges_guide_is_linked_and_covers_eval_path() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    doc = Path("docs/judges-guide.md").read_text(encoding="utf-8")

    assert "docs/judges-guide.md" in readme
    assert "3-minute judges guide" in readme
    assert "uv run anvil run scenarios/refund_agent.yaml" in doc
    assert "uv run anvil mcp harden" in doc
    assert "OpenAI is used in two ways" in doc
    assert "Why This Is a System, Not a Prompt" in doc


def test_issue_templates_cover_bug_feature_and_scenario_requests() -> None:
    template_paths = {
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/scenario_request.yml",
    }

    for path in template_paths:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        assert payload["name"]
        assert payload["description"]
        assert payload["body"]
