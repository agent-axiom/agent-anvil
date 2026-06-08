from __future__ import annotations

import tomllib
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
    assert "uv run anvil init --profile ci-safe" in readme
    assert "uv run anvil init --profile ci-safe" in doc
    assert "uv run anvil init --adapter http-python" in readme
    assert "uv run anvil init --adapter http-python" in doc
    assert "uv run anvil init --agent-url" in readme
    assert "--agent-url" in doc
    assert "--header" in doc
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
    assert "uv run anvil conformance external-agent" in cli_doc
    assert "uv run anvil doctor" in readme
    assert "uv run anvil doctor" in cli_doc
    assert "uv run anvil doctor scenarios/agent_anvil_starter.yaml --json" in cli_doc
    assert '--url "http://127.0.0.1:8080/anvil"' in cli_doc
    assert "protocol: http" in Path("docs/protocol.md").read_text(encoding="utf-8")
    assert "protocol: http" in Path("docs/scenarios.md").read_text(encoding="utf-8")
    assert '--header "Authorization=Bearer $ANVIL_AGENT_TOKEN"' in Path(
        "docs/conformance.md"
    ).read_text(encoding="utf-8")


def test_adapter_docs_are_linked_from_readme_and_cli_reference() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")
    cli_doc = Path("docs/cli.md").read_text(encoding="utf-8")
    adapters = Path("docs/adapters.md").read_text(encoding="utf-8")

    assert "docs/adapters.md" in readme
    assert "adapters.md" in artifacts
    assert "uv run anvil adapter list" in cli_doc
    assert "uv run anvil adapter add http-python" in readme
    assert "uv run anvil adapter add http-python" in cli_doc
    assert "uv run anvil adapter add openai-agents" in cli_doc
    assert "uv run anvil adapter add langgraph" in cli_doc
    assert "OpenAI Agents SDK" in adapters
    assert "LangGraph" in adapters
    assert "anvil.external" in adapters


def test_fastapi_http_agent_example_is_documented() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")
    example_doc = Path("docs/http-fastapi-agent.md").read_text(encoding="utf-8")

    assert "examples/http_fastapi_agent" in readme
    assert "http-fastapi-agent.md" in artifacts
    assert "uv run --with fastapi --with uvicorn" in example_doc
    assert "scenarios/http_fastapi_agent.yaml" in example_doc


def test_node_http_agent_example_is_documented() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")
    example_doc = Path("docs/node-http-agent.md").read_text(encoding="utf-8")

    assert "examples/node_http_agent" in readme
    assert "node-http-agent.md" in artifacts
    assert "npm --prefix examples/node_http_agent install" in example_doc
    assert "scenarios/node_http_agent.yaml" in example_doc


def test_openai_agents_sdk_agent_example_is_documented() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")
    example_doc = Path("docs/openai-agents-sdk-agent.md").read_text(encoding="utf-8")

    assert "examples/openai_agents_sdk_agent" in readme
    assert "openai-agents-sdk-agent.md" in artifacts
    assert "--with openai-agents --with fastapi --with uvicorn" in example_doc
    assert "ANVIL_OPENAI_AGENTS_MODE=openai" in example_doc
    assert "scenarios/openai_agents_sdk_agent.yaml" in example_doc


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
    assert "uv run anvil leaderboard inspect leaderboard_submission.json" in cli_doc
    assert "uv run anvil leaderboard reproduce leaderboard_submission.json" in cli_doc
    assert "leaderboard inspect leaderboard_submission.json" in readme
    assert "leaderboard reproduce leaderboard_submission.json" in readme
    assert "Hugging Face Dataset" in leaderboard_doc
    assert "LEADERBOARD_INDEX_URL" in leaderboard_doc
    assert "reproducibility checklist" in leaderboard_doc
    assert "review-first" in leaderboard_doc
    assert "Create Maintainer Rerun Attestation" in leaderboard_doc
    assert "trust-level filters" in leaderboard_doc
    assert "does not execute user agents" in space_readme
    assert "uv run anvil leaderboard pr leaderboard_submission.json" in cli_doc
    assert "--leaderboard-repo ../agent-anvil-leaderboard" in leaderboard_doc


def test_huggingface_space_invites_verified_submissions() -> None:
    app = Path("integrations/huggingface/leaderboard_space/app.py").read_text(encoding="utf-8")
    view = Path("integrations/huggingface/leaderboard_space/leaderboard_view.py").read_text(
        encoding="utf-8"
    )
    readme = Path("integrations/huggingface/leaderboard_space/README.md").read_text(
        encoding="utf-8"
    )

    for text in (app, readme):
        assert "Submit your agent" in text
        assert "agent-axiom/agent-anvil-demo-agent" in text
        assert "agent-anvil-leaderboard/pull/18" in text
        assert "filter" in text.lower()
        assert "sort" in text.lower()
        assert "freshness" in text.lower()
        assert "stale" in text.lower()
        assert "health" in text.lower()
        assert "benchmark" in text.lower()

    assert "DISPLAY_COLUMNS" in view
    for text in (app, readme, view):
        assert "self_reported" in text
        assert "github_actions" in text
        assert "maintainer_rerun" in text


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
            "https://github.com/agent-axiom/agent-anvil-demo-agent/actions/runs/26656805979" in text
        )
        assert "attested" in text
        assert "https://github.com/agent-axiom/agent-anvil-leaderboard/pull/18" in text


def test_submission_docs_surface_public_proof_path() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    submission = Path("docs/submission.md").read_text(encoding="utf-8")
    judges_guide = Path("docs/judges-guide.md").read_text(encoding="utf-8")

    for text in (readme, submission, judges_guide):
        assert "agent-anvil-demo-agent/actions/runs/26656805979" in text
        assert "agent-anvil-leaderboard/pull/18" in text
        assert "https://huggingface.co/spaces/ifif/agent-anvil-leaderboard" in text

    assert "Public proof path" in submission
    assert "Public end-to-end proof" in judges_guide


def test_leaderboard_submission_workflow_exports_verifiable_github_actions_row() -> None:
    workflow = Path("docs/examples/leaderboard-submission-workflow.yml").read_text(encoding="utf-8")

    assert "uvx --from git+https://github.com/agent-axiom/agent-anvil" in workflow
    assert "--require-trust github_actions" in workflow
    assert "PYTHONPATH: ${{ github.workspace }}" in workflow
    assert "GITHUB_STEP_SUMMARY" in workflow
    assert "id-token: write" in workflow
    assert "attestations: write" in workflow
    assert "actions/attest@v4" in workflow
    assert "subject-path: leaderboard_submission.json" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "submission/" in workflow
    assert "uv sync --group dev" not in workflow
    leaderboard_doc = Path("docs/leaderboard.md").read_text(encoding="utf-8")
    assert "gh attestation verify leaderboard_submission.json" in leaderboard_doc


def test_leaderboard_auto_pr_workflow_is_copy_pasteable() -> None:
    workflow = Path("docs/examples/leaderboard-auto-pr-workflow.yml").read_text(encoding="utf-8")
    leaderboard_doc = Path("docs/leaderboard.md").read_text(encoding="utf-8")

    assert "LEADERBOARD_PR_TOKEN" in workflow
    assert "repository: agent-axiom/agent-anvil-leaderboard" in workflow
    assert "path: leaderboard-repo" in workflow
    assert "token: ${{ secrets.LEADERBOARD_PR_TOKEN }}" in workflow
    assert "anvil leaderboard pr leaderboard_submission.json" in workflow
    assert "--pr-body-out agent-anvil-leaderboard-pr.md" in workflow
    assert "git push --set-upstream origin" in workflow
    assert "gh pr create" in workflow
    assert '--head "$branch"' in workflow
    assert "GH_TOKEN: ${{ secrets.LEADERBOARD_PR_TOKEN }}" in workflow
    assert "does not execute arbitrary user agents" in leaderboard_doc
    assert "docs/examples/leaderboard-auto-pr-workflow.yml" in leaderboard_doc


def test_leaderboard_index_workflow_exports_verification_reports() -> None:
    workflow = Path("docs/examples/leaderboard-index-workflow.yml").read_text(encoding="utf-8")
    leaderboard_doc = Path("docs/leaderboard.md").read_text(encoding="utf-8")

    assert "anvil leaderboard build submissions" in workflow
    assert "anvil leaderboard verify-all submissions" in workflow
    assert "--out github-run-verifications" in workflow
    assert "github-run-verifications" in workflow
    assert "Use `verify-all` in leaderboard maintainer CI" in leaderboard_doc


def test_leaderboard_uvx_examples_pin_current_release() -> None:
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    expected_ref = f"git+https://github.com/agent-axiom/agent-anvil@v{version}"

    for path in (
        Path("docs/examples/leaderboard-submission-workflow.yml"),
        Path("docs/examples/leaderboard-auto-pr-workflow.yml"),
        Path("docs/examples/leaderboard-index-workflow.yml"),
    ):
        text = path.read_text(encoding="utf-8")
        assert expected_ref in text
        assert "git+https://github.com/agent-axiom/agent-anvil \\" not in text


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


def test_trust_center_documents_security_privacy_and_stability() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    artifacts = Path("docs/artifacts.md").read_text(encoding="utf-8")
    contributing = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
    security = Path("SECURITY.md").read_text(encoding="utf-8")
    trust = Path("docs/trust.md").read_text(encoding="utf-8")
    privacy = Path("docs/privacy.md").read_text(encoding="utf-8")
    stability = Path("docs/stability.md").read_text(encoding="utf-8")
    schema_versioning = Path("docs/schema-versioning.md").read_text(encoding="utf-8")
    release_provenance = Path("docs/release-provenance.md").read_text(encoding="utf-8")

    for path in (
        "docs/trust.md",
        "docs/privacy.md",
        "docs/stability.md",
        "docs/schema-versioning.md",
        "docs/release-provenance.md",
        "SECURITY.md",
    ):
        assert path in readme

    for path in (
        "trust.md",
        "privacy.md",
        "stability.md",
        "schema-versioning.md",
        "release-provenance.md",
        "../SECURITY.md",
    ):
        assert path in artifacts

    assert "SECURITY.md" in contributing
    assert "Supported Versions" in security
    assert "Reporting a Vulnerability" in security
    assert "Do not publish secrets" in security
    assert "Trust Center" in trust
    assert "Stable Core" in trust
    assert "Experimental Helpers" in trust
    assert "OpenAI semantic grading" in privacy
    assert "ANVIL_REDACT_PATTERNS" in privacy
    assert "Local run artifacts keep raw traces" in privacy
    assert "Semantic Versioning" in stability
    assert "Deprecation Policy" in stability
    assert "agent-anvil.leaderboard.v1" in schema_versioning
    assert "anvil.trace.v1" in schema_versioning
    assert "Scenario files" in schema_versioning
    assert "Release Checklist" in release_provenance
    assert "GitHub Actions" in release_provenance
    assert "artifact attestation" in release_provenance


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
