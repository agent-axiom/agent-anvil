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

    assert "docs/init.md" in readme
    assert "uv run anvil init --agent-command" in readme
    assert "--pack tool-safety" in doc
    assert "post-pr-comment" in doc
    assert "--force" in doc


def test_packs_doc_is_linked_from_readme() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    doc = Path("docs/packs.md").read_text(encoding="utf-8")

    assert "docs/packs.md" in readme
    assert "uv run anvil pack list" in doc
    assert "tool-safety" in doc
    assert "destructive_tools" in doc
    assert "--risky-tool" in doc
    assert "--verification-tool" in doc


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
