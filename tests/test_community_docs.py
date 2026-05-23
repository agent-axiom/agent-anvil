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
    assert "MCP Tool Safety Audit" in artifacts
    assert "uv run anvil compare runs/baseline runs/latest" in cli_doc
    assert "uv run anvil mcp harden" in cli_doc


def test_leaderboard_docs_cover_public_huggingface_flow() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")
    cli_doc = Path("docs/cli.md").read_text(encoding="utf-8")
    leaderboard_doc = Path("docs/leaderboard.md").read_text(encoding="utf-8")
    space_readme = Path("integrations/huggingface/leaderboard_space/README.md").read_text(
        encoding="utf-8"
    )

    assert "docs/leaderboard.md" in readme
    assert "leaderboard build submissions" in readme
    assert "leaderboard-index-workflow.yml" in artifacts
    assert "uv run anvil leaderboard build submissions" in cli_doc
    assert "Hugging Face Dataset" in leaderboard_doc
    assert "LEADERBOARD_INDEX_URL" in leaderboard_doc
    assert "does not execute user agents" in space_readme
    assert "uv run anvil leaderboard pr leaderboard_submission.json" in cli_doc
    assert "--leaderboard-repo ../agent-anvil-leaderboard" in leaderboard_doc


def test_leaderboard_docs_reference_live_submissions_repo() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    leaderboard_doc = Path("docs/leaderboard.md").read_text(encoding="utf-8")
    workflow = Path("docs/examples/leaderboard-index-workflow.yml").read_text(encoding="utf-8")

    assert "https://github.com/agent-axiom/agent-anvil-leaderboard" in readme
    assert "https://github.com/agent-axiom/agent-anvil-leaderboard" in leaderboard_doc
    assert "uvx --from git+https://github.com/agent-axiom/agent-anvil" in workflow
    assert "uv sync --group dev" not in workflow


def test_leaderboard_docs_link_verified_end_to_end_demo() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    leaderboard_doc = Path("docs/leaderboard.md").read_text(encoding="utf-8")

    for text in (readme, leaderboard_doc):
        assert "https://github.com/agent-axiom/agent-anvil-demo-agent" in text
        assert (
            "https://github.com/agent-axiom/agent-anvil-demo-agent/actions/runs/26335581868" in text
        )
        assert "https://github.com/agent-axiom/agent-anvil-leaderboard/pull/1" in text


def test_leaderboard_submission_workflow_exports_verifiable_github_actions_row() -> None:
    workflow = Path("docs/examples/leaderboard-submission-workflow.yml").read_text(encoding="utf-8")

    assert "uvx --from git+https://github.com/agent-axiom/agent-anvil" in workflow
    assert "--require-trust github_actions" in workflow
    assert "PYTHONPATH: ${{ github.workspace }}" in workflow
    assert "GITHUB_STEP_SUMMARY" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "submission/" in workflow
    assert "uv sync --group dev" not in workflow


def test_paper_draft_links_reproducible_artifact() -> None:
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")
    paper = Path("paper/main.tex").read_text(encoding="utf-8")
    references = Path("paper/references.bib").read_text(encoding="utf-8")

    assert "../paper/main.tex" in artifacts
    assert "paper/tables.md" in artifacts
    assert "Agent Anvil: Trace-Centric CI Evaluation" in paper
    assert "experiments/paper.yaml" in paper
    assert "100.0\\% final-answer pass rate" in paper
    assert "30.0\\% trace-aware pass rate" in paper
    assert "yao2023react" in references
    assert "openaiAgentEvals" in references


def test_docs_separate_core_from_experimental_helpers() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    limits = Path("docs/limits.md").read_text(encoding="utf-8")

    assert "run -> trace -> check -> grade -> report -> CI" in readme
    assert "docs/limits.md" in readme
    assert "experimental helpers" in readme
    assert "Production-Useful Core" in limits
    assert "Experimental Helpers" in limits
    assert "do not treat it as" in limits
    assert "generic auto-fix engine" in limits
    assert "coverage-" in limits
    assert "guided fuzzing" in limits
    assert "They are not a" in limits
    assert "full MCP safety analyzer" in limits
    assert "run -> repair -> fix -> learn -> CI" not in readme


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
