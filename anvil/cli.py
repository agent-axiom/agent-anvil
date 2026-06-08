from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import typer

from anvil.adapter_templates import list_adapter_templates, write_adapter_template
from anvil.benchmark import format_rate_ci, load_benchmark_manifest, run_benchmark
from anvil.conformance import (
    parse_env_overrides,
    parse_header_overrides,
    run_external_agent_conformance,
    write_conformance_report,
)
from anvil.contracts import export_schema_contracts
from anvil.doctor import (
    render_doctor_github_summary,
    render_doctor_json,
    render_doctor_report,
    run_doctor,
    write_doctor_json,
)
from anvil.fix import generate_fix_patch
from anvil.flakiness import FlakyScenario
from anvil.fuzzing import fuzz_scenario_file
from anvil.ingest import ingest_jsonl_trace
from anvil.init import DEFAULT_SCENARIO_PATH, DEFAULT_WORKFLOW_PATH, initialize_project
from anvil.leaderboard import (
    LeaderboardValidationError,
    audit_leaderboard_submissions,
    build_leaderboard_index,
    export_leaderboard_submission,
    generate_leaderboard_reproduction_script,
    inspect_leaderboard_submission,
    prepare_leaderboard_pr_submission,
    validate_leaderboard_submission,
    verify_leaderboard_github_run,
    verify_leaderboard_github_runs,
)
from anvil.learning import load_trace, write_learned_scenario
from anvil.mcp_audit import audit_mcp_tools, load_mcp_tools, snapshot_mcp_tools
from anvil.mcp_repair import generate_mcp_repair, harden_mcp_server, render_mcp_harden_summary
from anvil.packs import DEFAULT_PACK_OUT, list_packs, write_pack
from anvil.pr_comment import write_pr_comment
from anvil.repair import generate_repair_plan
from anvil.runner import (
    FailureDelta,
    OpenAIKeyMissingError,
    compare_result_payload,
    compare_runs,
    default_semantic_grader,
    regenerate_report,
    run_suite,
)
from anvil.scenario import ExternalAgentConfig
from anvil.storage import ResultsArtifactError
from anvil.summary import generate_github_summary
from anvil.terminal import print_run_summary
from anvil.trace import TraceArtifactError
from anvil.trace_bridge import OpenAITracePayloadError, export_openai_trace, import_openai_trace

app = typer.Typer(help="Agent Anvil CI-first eval harness.")
adapter_app = typer.Typer(help="Generate external-agent adapter templates.")
mcp_app = typer.Typer(help="Audit MCP tools and generate safety scenarios.")
trace_app = typer.Typer(help="Import and export trace formats.")
pack_app = typer.Typer(help="List and add built-in scenario packs.")
ingest_app = typer.Typer(help="Ingest production agent logs into Anvil traces.")
paper_app = typer.Typer(help="Reproduce paper benchmark artifacts.")
leaderboard_app = typer.Typer(help="Export leaderboard submission artifacts.")
schema_app = typer.Typer(help="Export stable JSON Schema contracts.")
conformance_app = typer.Typer(help="Check external agent protocol compatibility.")
app.add_typer(adapter_app, name="adapter")
app.add_typer(mcp_app, name="mcp")
app.add_typer(trace_app, name="trace")
app.add_typer(pack_app, name="pack")
app.add_typer(ingest_app, name="ingest")
app.add_typer(paper_app, name="paper")
app.add_typer(leaderboard_app, name="leaderboard")
app.add_typer(schema_app, name="schema")
app.add_typer(conformance_app, name="conformance")


@contextmanager
def _handle_results_artifact_errors() -> Iterator[None]:
    try:
        yield
    except ResultsArtifactError as error:
        typer.echo(f"Invalid results artifact: {error}", err=True)
        raise typer.Exit(1) from error


@contextmanager
def _handle_trace_artifact_errors() -> Iterator[None]:
    try:
        yield
    except TraceArtifactError as error:
        typer.echo(f"Invalid trace artifact: {error}", err=True)
        raise typer.Exit(1) from error


@contextmanager
def _handle_openai_trace_payload_errors() -> Iterator[None]:
    try:
        yield
    except OpenAITracePayloadError as error:
        typer.echo(f"Invalid OpenAI trace payload: {error}", err=True)
        raise typer.Exit(1) from error


PASSING_RATE = 100.0
TRIALS_OPTION = typer.Option(None, "--trials", min=1, help="Override trial count.")
RUNS_DIR_OPTION = typer.Option(Path("runs"), "--runs-dir", help="Run artifact directory.")
OFFLINE_OPTION = typer.Option(False, "--offline", help="Use local heuristic grading only.")
REDACT_OPTION = typer.Option(
    None,
    "--redact/--no-redact",
    help="Redact sensitive scenario and trace values before OpenAI semantic grading.",
)
GITHUB_SUMMARY_OPTION = typer.Option(
    False,
    "--github",
    help="Render Markdown optimized for GitHub Step Summary.",
)
COMPARE_JSON_OPTION = typer.Option(False, "--json", help="Render compare result as JSON.")
COMPARE_OUT_OPTION = typer.Option(None, "--out", help="Write compare result JSON to this path.")
AGENT_MODE_OPTION = typer.Option(
    None,
    "--agent-mode",
    help="Agent execution mode for demo agents: offline, openai, or auto.",
)
LEARN_OUT_OPTION = typer.Option(..., "--out", help="Write the learned scenario YAML here.")
FIX_OUT_OPTION = typer.Option(..., "--out", help="Write the generated patch diff here.")
MCP_REPORT_OPTION = typer.Option(..., "--report", help="Write the MCP audit Markdown report here.")
MCP_COMMAND_OPTION = typer.Option(None, "--command", help="MCP stdio server command to snapshot.")
MCP_COMMAND_JSON_OPTION = typer.Option(
    None,
    "--command-json",
    help="JSON array MCP stdio server command to snapshot without shell-like parsing.",
)
MCP_SNAPSHOT_OUT_OPTION = typer.Option(..., "--out", help="Write MCP tools snapshot here.")
MCP_AUDIT_OUT_OPTION = typer.Option(None, "--audit-out", help="Optionally write audit scenarios.")
MCP_SNAPSHOT_REPORT_OPTION = typer.Option(None, "--report", help="Optionally write audit report.")
MCP_REPAIR_OUT_OPTION = typer.Option(..., "--out", help="Write MCP repair Markdown here.")
MCP_HARDEN_SNAPSHOT_OUT_OPTION = typer.Option(
    ...,
    "--snapshot-out",
    help="Write MCP tools snapshot here.",
)
MCP_HARDEN_AUDIT_OUT_OPTION = typer.Option(
    ...,
    "--audit-out",
    help="Write generated MCP safety scenarios here.",
)
MCP_HARDEN_AUDIT_REPORT_OPTION = typer.Option(
    ...,
    "--audit-report",
    help="Write MCP audit Markdown here.",
)
MCP_HARDEN_REPAIR_OUT_OPTION = typer.Option(
    ...,
    "--repair-out",
    help="Write MCP repair Markdown here.",
)
MCP_HARDEN_GITHUB_SUMMARY_OPTION = typer.Option(
    False,
    "--github-summary",
    help="Append MCP harden Markdown summary to GITHUB_STEP_SUMMARY when available.",
)
MCP_TIMEOUT_OPTION = typer.Option(10.0, "--timeout", min=0.1, help="MCP response timeout seconds.")
TRACE_FORMAT_OPTION = typer.Option("openai-trace", "--format", help="Trace format.")
FIX_PROMPT_OPTION = typer.Option(None, "--prompt", help="Prompt file to patch in the diff.")
FIX_TOOLS_OPTION = typer.Option(None, "--tools", help="Tool definition file to patch in the diff.")
TRACE_EXPORT_OUT_OPTION = typer.Option(..., "--out", help="Write exported trace JSON here.")
TRACE_IMPORT_OUT_OPTION = typer.Option(..., "--out", help="Write imported Anvil trace run here.")
LEARN_JSONL_RUNS_DIR_OPTION = typer.Option(
    Path("runs/learned"),
    "--runs-dir",
    help="Write intermediate traces here when learning from JSONL.",
)
FUZZ_OUT_OPTION = typer.Option(..., "--out", help="Write the fuzzed scenario YAML here.")
FUZZ_MUTATIONS_OPTION = typer.Option(10, "--mutations", min=1, help="Number of mutations.")
FUZZ_FOCUS_OPTION = typer.Option("tool_safety", "--focus", help="Mutation focus.")
PR_COMMENT_OUT_OPTION = typer.Option(..., "--out", help="Write PR-ready Markdown here.")
PR_COMMENT_COMPARE_OPTION = typer.Option(
    None,
    "--compare",
    help="Optional compare JSON artifact to include in the PR comment.",
)
DOCTOR_SCENARIO_ARGUMENT = typer.Argument(
    DEFAULT_SCENARIO_PATH,
    help="Scenario file to diagnose.",
)
DOCTOR_WORKFLOW_OPTION = typer.Option(
    DEFAULT_WORKFLOW_PATH,
    "--workflow",
    help="GitHub Actions workflow to check.",
)
DOCTOR_MAX_STEPS_OPTION = typer.Option(
    8,
    "--max-steps",
    min=1,
    help="Maximum trace steps allowed during conformance checks.",
)
DOCTOR_SKIP_CONFORMANCE_OPTION = typer.Option(
    False,
    "--skip-conformance",
    help="Skip active external-agent conformance checks.",
)
DOCTOR_SKIP_WORKFLOW_OPTION = typer.Option(
    False,
    "--skip-workflow",
    help="Skip GitHub Actions workflow checks for local-only diagnostics.",
)
DOCTOR_JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Print the doctor report as JSON.",
)
DOCTOR_OUT_OPTION = typer.Option(
    None,
    "--out",
    help="Write the doctor JSON report here.",
)
DOCTOR_GITHUB_SUMMARY_OPTION = typer.Option(
    False,
    "--github-summary",
    help="Append doctor Markdown summary to GITHUB_STEP_SUMMARY when available.",
)
INIT_AGENT_COMMAND_OPTION = typer.Option(
    None,
    "--agent-command",
    help="Command Agent Anvil should run for your external JSONL agent.",
)
INIT_AGENT_URL_OPTION = typer.Option(
    None,
    "--agent-url",
    help="HTTP endpoint URL Agent Anvil should POST scenario payloads to.",
)
INIT_ADAPTER_OPTION = typer.Option(
    None,
    "--adapter",
    help="Generate a starter adapter template and wire it into the starter scenario.",
)
INIT_ADAPTER_OUT_OPTION = typer.Option(
    None,
    "--adapter-out",
    help="Adapter path to create when using --adapter. Defaults to adapters/<name>_adapter.py.",
)
INIT_HEADER_OPTION = typer.Option(
    None,
    "--header",
    help="HTTP request header for --agent-url. Repeatable KEY=VALUE.",
)
PACK_AGENT_COMMAND_OPTION = typer.Option(
    ...,
    "--agent-command",
    help="Command Agent Anvil should run for your external JSONL agent.",
)
INIT_SCENARIO_OPTION = typer.Option(
    DEFAULT_SCENARIO_PATH,
    "--scenario",
    help="Starter scenario path to create.",
)
INIT_WORKFLOW_OPTION = typer.Option(
    DEFAULT_WORKFLOW_PATH,
    "--workflow",
    help="GitHub Actions workflow path to create.",
)
INIT_FORCE_OPTION = typer.Option(False, "--force", help="Overwrite existing generated files.")
INIT_POST_PR_COMMENT_OPTION = typer.Option(
    False,
    "--post-pr-comment",
    help="Configure the generated workflow to publish Agent Anvil PR comments.",
)
INIT_PROFILE_OPTION = typer.Option(
    None,
    "--profile",
    help="Use an opinionated bootstrap profile, such as ci-safe.",
)
INIT_PACK_OPTION = typer.Option(
    None,
    "--pack",
    help="Use a built-in starter scenario pack, such as tool-safety.",
)
PACK_OUT_OPTION = typer.Option(DEFAULT_PACK_OUT, "--out", help="Write the scenario pack here.")
RISKY_TOOL_OPTION = typer.Option(
    None,
    "--risky-tool",
    help="Risky/destructive tool to include in a generated scenario pack. Repeatable.",
)
VERIFICATION_TOOL_OPTION = typer.Option(
    None,
    "--verification-tool",
    help="Verification tool required before risky tools. Repeatable.",
)
APPROVAL_TOOL_OPTION = typer.Option(
    None,
    "--approval-required-tool",
    help="Risky tool that should require human approval. Repeatable.",
)
INGEST_SCENARIO_ID_OPTION = typer.Option(..., "--scenario-id", help="Scenario id for the trace.")
INGEST_INPUT_OPTION = typer.Option(..., "--input", help="Original user input for the trace.")
INGEST_OUT_OPTION = typer.Option(..., "--out", help="Write imported run artifacts here.")
INGEST_TRIAL_OPTION = typer.Option(1, "--trial", min=1, help="Trial number for the trace.")
BENCH_RUNS_DIR_OPTION = typer.Option(
    Path("runs/bench"),
    "--runs-dir",
    help="Run artifact directory for benchmark suite runs.",
)
BENCH_OUT_OPTION = typer.Option(
    None,
    "--out",
    help="Write benchmark JSON results here. Defaults to manifest output.json.",
)
BENCH_MARKDOWN_OUT_OPTION = typer.Option(
    None,
    "--markdown-out",
    help="Write benchmark Markdown results here. Defaults to manifest output.markdown.",
)
PAPER_MANIFEST_OPTION = typer.Option(
    Path("experiments/paper.yaml"),
    "--manifest",
    help="Paper benchmark manifest to reproduce.",
)
PAPER_RUNS_DIR_OPTION = typer.Option(
    Path("runs/paper-benchmark"),
    "--runs-dir",
    help="Run artifact directory for reproduced paper traces.",
)
PAPER_OFFLINE_OPTION = typer.Option(
    True,
    "--offline/--openai",
    help="Use offline grading by default; pass --openai to reproduce with OpenAI grading.",
)
LEADERBOARD_MANIFEST_OPTION = typer.Option(
    ...,
    "--manifest",
    help="Benchmark manifest used to produce the results JSON.",
)
LEADERBOARD_OUT_OPTION = typer.Option(
    Path("leaderboard_submission.json"),
    "--out",
    help="Write leaderboard submission JSON here.",
)
LEADERBOARD_AGENT_NAME_OPTION = typer.Option(
    ...,
    "--agent-name",
    help="Human-readable agent name for the leaderboard.",
)
LEADERBOARD_AGENT_VERSION_OPTION = typer.Option(
    "",
    "--agent-version",
    help="Agent version, model, prompt version, or release label.",
)
LEADERBOARD_REPO_URL_OPTION = typer.Option(
    "",
    "--repo-url",
    help="Public repository URL for the evaluated agent.",
)
LEADERBOARD_COMMIT_SHA_OPTION = typer.Option(
    "",
    "--commit-sha",
    help="Commit SHA for the evaluated agent.",
)
LEADERBOARD_NOTES_OPTION = typer.Option(
    "",
    "--notes",
    help="Short public notes for the leaderboard submission.",
)
LEADERBOARD_VERIFY_ARTIFACTS_OPTION = typer.Option(
    True,
    "--artifacts/--no-artifacts",
    help="Verify local artifact hashes referenced by the submission.",
)
LEADERBOARD_REQUIRE_TRUST_OPTION = typer.Option(
    None,
    "--require-trust",
    help="Require a trust level such as self_reported or github_actions.",
)
LEADERBOARD_VERIFY_GITHUB_RUN_OPTION = typer.Option(
    False,
    "--github-run/--no-github-run",
    help="Verify GitHub Actions run metadata for github_actions submissions.",
)
LEADERBOARD_VERIFY_RUN_JSON_OPTION = typer.Option(
    False,
    "--json",
    help="Print the GitHub run verification report as JSON.",
)
LEADERBOARD_VERIFY_RUN_OUT_OPTION = typer.Option(
    None,
    "--out",
    help="Write the GitHub run verification report JSON here.",
)
LEADERBOARD_VERIFY_ALL_OUT_OPTION = typer.Option(
    ...,
    "--out",
    help="Write one GitHub run verification report JSON file per submission here.",
)
LEADERBOARD_AUDIT_JSON_OUT_OPTION = typer.Option(
    Path("leaderboard_audit.json"),
    "--json-out",
    help="Write the leaderboard maintainer audit JSON report here.",
)
LEADERBOARD_AUDIT_MARKDOWN_OUT_OPTION = typer.Option(
    Path("leaderboard_audit.md"),
    "--markdown-out",
    help="Write the leaderboard maintainer audit Markdown report here.",
)
LEADERBOARD_AUDIT_FAIL_ON_OPTION = typer.Option(
    "review",
    "--fail-on",
    help="Exit non-zero on review, reject, or never. Default fails on review and reject.",
)
LEADERBOARD_INDEX_OUT_OPTION = typer.Option(
    Path("leaderboard.csv"),
    "--out",
    help="Write leaderboard CSV index here.",
)
LEADERBOARD_INDEX_JSON_OUT_OPTION = typer.Option(
    Path("leaderboard.json"),
    "--json-out",
    help="Write leaderboard JSON index here.",
)
LEADERBOARD_BUILD_VERIFY_ARTIFACTS_OPTION = typer.Option(
    False,
    "--artifacts/--no-artifacts",
    help="Verify local artifact hashes while building the index.",
)
LEADERBOARD_REPO_OPTION = typer.Option(
    Path("../agent-anvil-leaderboard"),
    "--leaderboard-repo",
    help="Local checkout of agent-axiom/agent-anvil-leaderboard.",
)
LEADERBOARD_SUBMISSION_NAME_OPTION = typer.Option(
    None,
    "--submission-name",
    help="Output file name under submissions/. Defaults to a slug of the agent name.",
)
LEADERBOARD_FORCE_OPTION = typer.Option(False, "--force", help="Overwrite an existing submission.")
LEADERBOARD_INSPECT_OUT_OPTION = typer.Option(
    None,
    "--out",
    help="Write a Markdown inspection report instead of printing the full report.",
)
LEADERBOARD_REPRODUCE_OUT_OPTION = typer.Option(
    Path("reproduce_leaderboard_submission.sh"),
    "--out",
    help="Write a reviewable shell script for independently reproducing a submission.",
)
LEADERBOARD_PR_BODY_OUT_OPTION = typer.Option(
    None,
    "--pr-body-out",
    help="Write a reviewable pull-request body for gh pr create --body-file.",
)
LEARN_JSONL_FILE_ARGUMENT = typer.Argument(None)
SCHEMA_OUT_OPTION = typer.Option(Path("schemas"), "--out", help="Write schema files here.")
ADAPTER_OUT_OPTION = typer.Option(..., "--out", help="Write the adapter template here.")
ADAPTER_FORCE_OPTION = typer.Option(False, "--force", help="Overwrite an existing adapter file.")
CONFORMANCE_AGENT_COMMAND_OPTION = typer.Option(
    None,
    "--agent-command",
    help="External JSONL agent command to run.",
)
CONFORMANCE_URL_OPTION = typer.Option(
    None,
    "--url",
    help="HTTP agent endpoint URL to POST conformance payloads to.",
)
CONFORMANCE_HEADER_OPTION = typer.Option(
    None,
    "--header",
    help="HTTP request header for --url. Repeatable KEY=VALUE.",
)
CONFORMANCE_CWD_OPTION = typer.Option(
    None,
    "--cwd",
    help="Working directory for the external agent command.",
)
CONFORMANCE_ENV_OPTION = typer.Option(
    None,
    "--env",
    help="Environment override for the external agent command. Repeatable KEY=VALUE.",
)
CONFORMANCE_TIMEOUT_OPTION = typer.Option(
    10,
    "--timeout",
    min=1,
    help="External agent command timeout seconds.",
)
CONFORMANCE_MAX_STEPS_OPTION = typer.Option(
    8,
    "--max-steps",
    min=1,
    help="Maximum trace events accepted during conformance.",
)
CONFORMANCE_OUT_OPTION = typer.Option(
    None,
    "--out",
    help="Write a Markdown conformance report here.",
)


@schema_app.command("export")
def schema_export(out: Path = SCHEMA_OUT_OPTION) -> None:
    for path in export_schema_contracts(out):
        typer.echo(f"Wrote {_display_path(path)}")


@adapter_app.command("list")
def adapter_list() -> None:
    for template in list_adapter_templates():
        typer.echo(f"{template.name}: {template.description}")
        typer.echo(f"  {template.dependency_hint}")


@adapter_app.command("add")
def adapter_add(
    template_name: str,
    out: Path = ADAPTER_OUT_OPTION,
    force: bool = ADAPTER_FORCE_OPTION,
) -> None:
    try:
        adapter_path = write_adapter_template(template_name, out_path=out, force=force)
    except (FileExistsError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Wrote adapter template: {_display_path(adapter_path)}")
    typer.echo(
        "Next: edit the generated adapter, then run "
        f'`uv run anvil conformance external-agent --agent-command "python {adapter_path}"`.'
    )


@conformance_app.command("external-agent")
def conformance_external_agent(
    agent_command: str | None = CONFORMANCE_AGENT_COMMAND_OPTION,
    url: str | None = CONFORMANCE_URL_OPTION,
    header: list[str] | None = CONFORMANCE_HEADER_OPTION,
    cwd: Path | None = CONFORMANCE_CWD_OPTION,
    env: list[str] | None = CONFORMANCE_ENV_OPTION,
    timeout: int = CONFORMANCE_TIMEOUT_OPTION,
    max_steps: int = CONFORMANCE_MAX_STEPS_OPTION,
    out: Path | None = CONFORMANCE_OUT_OPTION,
) -> None:
    try:
        env_overrides = parse_env_overrides(env)
        header_overrides = parse_header_overrides(header)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error

    if bool(agent_command) == bool(url):
        typer.echo("Use either --agent-command or --url.", err=True)
        raise typer.Exit(2)

    if url is not None and (cwd is not None or env_overrides):
        typer.echo("--cwd and --env only apply to --agent-command.", err=True)
        raise typer.Exit(2)

    if url is not None:
        config = ExternalAgentConfig(
            protocol="http",
            url=url,
            headers=header_overrides,
            timeout_seconds=timeout,
        )
    else:
        config = ExternalAgentConfig(
            command=agent_command,
            timeout_seconds=timeout,
            cwd=str(cwd) if cwd is not None else None,
            env=env_overrides,
        )

    result = run_external_agent_conformance(
        config,
        max_steps=max_steps,
    )
    status = "PASS" if result.passed else "FAIL"
    typer.echo(f"External agent conformance: {status}")
    for check in result.checks:
        check_status = "PASS" if check.passed else "FAIL"
        typer.echo(f"- {check.name}: {check_status} - {check.message}")
    if out is not None:
        write_conformance_report(result, out)
        typer.echo(f"Wrote conformance report: {_display_path(out)}")
    if not result.passed:
        raise typer.Exit(1)


@app.command()
def doctor(
    scenario_file: Path = DOCTOR_SCENARIO_ARGUMENT,
    workflow: Path = DOCTOR_WORKFLOW_OPTION,
    max_steps: int = DOCTOR_MAX_STEPS_OPTION,
    skip_conformance: bool = DOCTOR_SKIP_CONFORMANCE_OPTION,
    skip_workflow: bool = DOCTOR_SKIP_WORKFLOW_OPTION,
    json_output: bool = DOCTOR_JSON_OPTION,
    out: Path | None = DOCTOR_OUT_OPTION,
    github_summary: bool = DOCTOR_GITHUB_SUMMARY_OPTION,
) -> None:
    report = run_doctor(
        scenario_file,
        workflow_path=workflow,
        max_steps=max_steps,
        skip_conformance=skip_conformance,
        skip_workflow=skip_workflow,
    )
    if out is not None:
        write_doctor_json(report, out)
    if json_output:
        typer.echo(render_doctor_json(report), nl=False)
    else:
        typer.echo(render_doctor_report(report))
        if out is not None:
            typer.echo(f"Wrote doctor report: {_display_path(out)}")
    if github_summary:
        _write_github_summary(render_doctor_github_summary(report))
    if not report.passed:
        raise typer.Exit(1)


@app.command()
def init(
    agent_command: str | None = INIT_AGENT_COMMAND_OPTION,
    agent_url: str | None = INIT_AGENT_URL_OPTION,
    adapter: str | None = INIT_ADAPTER_OPTION,
    adapter_out: Path | None = INIT_ADAPTER_OUT_OPTION,
    header: list[str] | None = INIT_HEADER_OPTION,
    scenario_path: Path = INIT_SCENARIO_OPTION,
    workflow_path: Path = INIT_WORKFLOW_OPTION,
    force: bool = INIT_FORCE_OPTION,
    post_pr_comment: bool = INIT_POST_PR_COMMENT_OPTION,
    profile: str | None = INIT_PROFILE_OPTION,
    pack: str | None = INIT_PACK_OPTION,
    risky_tools: list[str] | None = RISKY_TOOL_OPTION,
    verification_tools: list[str] | None = VERIFICATION_TOOL_OPTION,
    approval_required_tools: list[str] | None = APPROVAL_TOOL_OPTION,
) -> None:
    try:
        headers = parse_header_overrides(header)
        effective_adapter = adapter or (
            "http-python"
            if profile == "ci-safe" and agent_command is None and agent_url is None
            else None
        )
        written_paths = initialize_project(
            agent_command=agent_command,
            agent_url=agent_url,
            adapter=adapter,
            adapter_out=adapter_out,
            headers=headers,
            scenario_path=scenario_path,
            workflow_path=workflow_path,
            force=force,
            post_pr_comment=post_pr_comment,
            profile=profile,
            pack=pack,
            risky_tools=risky_tools,
            verification_tools=verification_tools,
            approval_required_tools=approval_required_tools,
        )
    except (FileExistsError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    for path in written_paths:
        typer.echo(f"Wrote {path}")
    if effective_adapter is not None:
        typer.echo(
            "Next: edit the generated adapter, then run "
            f"`uv run anvil conformance external-agent --agent-command "
            f'"python {written_paths[-1].as_posix()}"`.'
        )
        typer.echo(
            f"Then edit the starter scenario and run `uv run anvil run {scenario_path} --offline`."
        )
    elif agent_url is not None:
        typer.echo(
            "Next: start your HTTP agent endpoint, then run "
            f'`uv run anvil conformance external-agent --url "{agent_url}"`.'
        )
        typer.echo(
            f"Then edit the starter scenario and run `uv run anvil run {scenario_path} --offline`."
        )
    else:
        typer.echo(
            "Next: edit the starter scenario, then run "
            f"`uv run anvil run {scenario_path} --offline`."
        )


@pack_app.command("list")
def pack_list() -> None:
    for scenario_pack in list_packs():
        typer.echo(f"{scenario_pack.name}: {scenario_pack.description}")


@pack_app.command("add")
def pack_add(
    pack_name: str,
    agent_command: str = PACK_AGENT_COMMAND_OPTION,
    out: Path = PACK_OUT_OPTION,
    force: bool = INIT_FORCE_OPTION,
    risky_tools: list[str] | None = RISKY_TOOL_OPTION,
    verification_tools: list[str] | None = VERIFICATION_TOOL_OPTION,
    approval_required_tools: list[str] | None = APPROVAL_TOOL_OPTION,
) -> None:
    try:
        pack_path = write_pack(
            pack_name,
            agent_command=agent_command,
            out_path=out,
            force=force,
            risky_tools=risky_tools,
            verification_tools=verification_tools,
            approval_required_tools=approval_required_tools,
        )
    except (FileExistsError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Wrote {pack_path}")


@app.command()
def run(
    scenario_file: Path,
    trials: int | None = TRIALS_OPTION,
    runs_dir: Path = RUNS_DIR_OPTION,
    offline: bool = OFFLINE_OPTION,
    redact: bool | None = REDACT_OPTION,
    agent_mode: str | None = AGENT_MODE_OPTION,
) -> None:
    try:
        semantic_grader = default_semantic_grader(offline=offline, redact=redact)
    except OpenAIKeyMissingError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error

    result = run_suite(
        scenario_file,
        runs_dir=runs_dir,
        trials_override=trials,
        semantic_grader=semantic_grader,
        agent_mode=agent_mode,
    )
    print_run_summary(
        result,
        command=_run_command(
            scenario_file=scenario_file,
            runs_dir=runs_dir,
            trials=trials,
            offline=offline,
            redact=redact,
            agent_mode=agent_mode,
            failed=result.pass_rate < PASSING_RATE,
        ),
    )
    if result.pass_rate < PASSING_RATE:
        raise typer.Exit(1)


@app.command()
def bench(
    manifest_file: Path,
    runs_dir: Path = BENCH_RUNS_DIR_OPTION,
    out: Path | None = BENCH_OUT_OPTION,
    markdown_out: Path | None = BENCH_MARKDOWN_OUT_OPTION,
    offline: bool = OFFLINE_OPTION,
    redact: bool | None = REDACT_OPTION,
    agent_mode: str | None = AGENT_MODE_OPTION,
) -> None:
    try:
        result = run_benchmark(
            manifest_file,
            offline=offline,
            runs_dir=runs_dir,
            out_json=out,
            out_markdown=markdown_out,
            agent_mode=agent_mode,
            redact=redact,
        )
    except OpenAIKeyMissingError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error

    typer.echo(f"Benchmark: {result.name}")
    typer.echo(f"Total trials: {result.total_trials}")
    final_answer_rate = format_rate_ci(
        result.final_answer_pass_rate,
        result.final_answer_pass_rate_ci_low,
        result.final_answer_pass_rate_ci_high,
    )
    trace_aware_rate = format_rate_ci(
        result.trace_aware_pass_rate,
        result.trace_aware_pass_rate_ci_low,
        result.trace_aware_pass_rate_ci_high,
    )
    missed_failure_rate = format_rate_ci(
        result.answer_only_missed_failure_rate,
        result.answer_only_missed_failure_rate_ci_low,
        result.answer_only_missed_failure_rate_ci_high,
    )
    typer.echo(f"Final-answer baseline pass rate: {final_answer_rate}")
    typer.echo(f"Trace-aware Agent Anvil pass rate: {trace_aware_rate}")
    typer.echo(f"Answer-only missed failures: {result.answer_only_missed_failures}")
    typer.echo(f"Answer-only missed failure rate: {missed_failure_rate}")


@paper_app.command("reproduce")
def paper_reproduce(
    manifest_file: Path = PAPER_MANIFEST_OPTION,
    runs_dir: Path = PAPER_RUNS_DIR_OPTION,
    offline: bool = PAPER_OFFLINE_OPTION,
    redact: bool | None = REDACT_OPTION,
    agent_mode: str | None = AGENT_MODE_OPTION,
) -> None:
    try:
        result = run_benchmark(
            manifest_file,
            offline=offline,
            runs_dir=runs_dir,
            redact=redact,
            agent_mode=agent_mode,
        )
    except OpenAIKeyMissingError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error

    manifest = load_benchmark_manifest(manifest_file)
    final_answer_rate = format_rate_ci(
        result.final_answer_pass_rate,
        result.final_answer_pass_rate_ci_low,
        result.final_answer_pass_rate_ci_high,
    )
    trace_aware_rate = format_rate_ci(
        result.trace_aware_pass_rate,
        result.trace_aware_pass_rate_ci_low,
        result.trace_aware_pass_rate_ci_high,
    )
    missed_failure_rate = format_rate_ci(
        result.answer_only_missed_failure_rate,
        result.answer_only_missed_failure_rate_ci_low,
        result.answer_only_missed_failure_rate_ci_high,
    )
    typer.echo("Reproduced Agent Anvil paper artifacts")
    typer.echo(f"Benchmark: {result.name}")
    typer.echo(f"Total trials: {result.total_trials}")
    typer.echo(f"Final-answer baseline pass rate: {final_answer_rate}")
    typer.echo(f"Trace-aware Agent Anvil pass rate: {trace_aware_rate}")
    typer.echo(f"Answer-only missed failures: {result.answer_only_missed_failures}")
    typer.echo(f"Answer-only missed failure rate: {missed_failure_rate}")
    typer.echo(f"Results JSON: {_display_path(manifest.output.json_path)}")
    typer.echo(f"Results Markdown: {_display_path(manifest.output.markdown)}")
    typer.echo(f"Tables: {_display_path(manifest.output.tables)}")
    typer.echo(f"Runs: {_display_path(runs_dir)}")
    typer.echo("Evaluator ablation:")
    for entry in result.evaluator_ablation:
        typer.echo(
            f"- {entry.evaluator}: {entry.pass_rate:.1f}% pass; "
            f"{entry.answer_only_missed_failures} answer-only missed failures"
        )


@leaderboard_app.command("export")
def leaderboard_export(
    results_json: Path,
    manifest_file: Path = LEADERBOARD_MANIFEST_OPTION,
    out: Path = LEADERBOARD_OUT_OPTION,
    agent_name: str = LEADERBOARD_AGENT_NAME_OPTION,
    agent_version: str = LEADERBOARD_AGENT_VERSION_OPTION,
    repo_url: str = LEADERBOARD_REPO_URL_OPTION,
    commit_sha: str = LEADERBOARD_COMMIT_SHA_OPTION,
    notes: str = LEADERBOARD_NOTES_OPTION,
) -> None:
    submission = export_leaderboard_submission(
        results_json=results_json,
        manifest_path=manifest_file,
        out_path=out,
        agent_name=agent_name,
        agent_version=agent_version,
        repo_url=repo_url,
        commit_sha=commit_sha,
        notes=notes,
    )
    typer.echo(f"Wrote leaderboard submission: {_display_path(out)}")
    typer.echo(f"Trust level: {submission.verification.trust_level}")
    typer.echo(f"Evidence SHA-256: {submission.verification.evidence_sha256}")
    typer.echo(f"Benchmark: {submission.benchmark.name}")
    typer.echo(f"Total trials: {submission.metrics.total_trials}")
    typer.echo(f"Trace-aware pass rate: {submission.metrics.trace_aware_pass_rate:.1f}%")


@leaderboard_app.command("validate")
def leaderboard_validate(
    submission_file: Path,
    verify_artifacts: bool = LEADERBOARD_VERIFY_ARTIFACTS_OPTION,
    require_trust_level: str | None = LEADERBOARD_REQUIRE_TRUST_OPTION,
    verify_github_run: bool = LEADERBOARD_VERIFY_GITHUB_RUN_OPTION,
) -> None:
    try:
        submission = validate_leaderboard_submission(
            submission_file,
            verify_artifacts=verify_artifacts,
            require_trust_level=require_trust_level,
            verify_github_run=verify_github_run,
        )
    except LeaderboardValidationError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    typer.echo("Leaderboard submission is valid")
    typer.echo(f"Trust level: {submission.verification.trust_level}")
    typer.echo(f"Evidence SHA-256: {submission.verification.evidence_sha256}")
    typer.echo(f"Benchmark: {submission.benchmark.name}")
    typer.echo(f"Trace-aware pass rate: {submission.metrics.trace_aware_pass_rate:.1f}%")
    if verify_github_run:
        status = (
            "verified" if submission.verification.trust_level == "github_actions" else "not checked"
        )
        typer.echo(f"GitHub run: {status}")


@leaderboard_app.command("verify-run")
def leaderboard_verify_run(
    submission_file: Path,
    as_json: bool = LEADERBOARD_VERIFY_RUN_JSON_OPTION,
    out: Path | None = LEADERBOARD_VERIFY_RUN_OUT_OPTION,
) -> None:
    try:
        report = verify_leaderboard_github_run(submission_file)
    except LeaderboardValidationError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    report_json = report.model_dump_json(indent=2)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report_json, encoding="utf-8")
    if as_json:
        typer.echo(report_json)
        return
    if out is not None:
        typer.echo(f"Wrote GitHub run verification report: {_display_path(out)}")
    typer.echo("GitHub Actions run is verified")
    typer.echo(f"Repository: {report.github_repository}")
    typer.echo(f"SHA: {report.github_sha}")
    typer.echo(f"Run: {report.github_run_url}")
    typer.echo(f"Evidence SHA-256: {report.evidence_sha256}")


@leaderboard_app.command("verify-all")
def leaderboard_verify_all(
    submissions_dir: Path,
    out: Path = LEADERBOARD_VERIFY_ALL_OUT_OPTION,
) -> None:
    try:
        reports = verify_leaderboard_github_runs(submissions_dir, out_dir=out)
    except LeaderboardValidationError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    for report_path in reports:
        typer.echo(f"Wrote GitHub run verification report: {_display_path(report_path)}")
    typer.echo(f"Verified GitHub Actions runs: {len(reports)}")


@leaderboard_app.command("audit")
def leaderboard_audit(
    submissions_dir: Path,
    verify_artifacts: bool = LEADERBOARD_BUILD_VERIFY_ARTIFACTS_OPTION,
    verify_github_run: bool = LEADERBOARD_VERIFY_GITHUB_RUN_OPTION,
    json_out: Path = LEADERBOARD_AUDIT_JSON_OUT_OPTION,
    markdown_out: Path = LEADERBOARD_AUDIT_MARKDOWN_OUT_OPTION,
    fail_on: Literal["review", "reject", "never"] = LEADERBOARD_AUDIT_FAIL_ON_OPTION,
) -> None:
    try:
        audit = audit_leaderboard_submissions(
            submissions_dir,
            verify_artifacts=verify_artifacts,
            verify_github_run=verify_github_run,
        )
    except LeaderboardValidationError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(audit.model_dump_json(indent=2), encoding="utf-8")
    markdown_out.parent.mkdir(parents=True, exist_ok=True)
    markdown_out.write_text(audit.markdown, encoding="utf-8")
    typer.echo(f"Wrote leaderboard audit JSON: {_display_path(json_out)}")
    typer.echo(f"Wrote leaderboard audit Markdown: {_display_path(markdown_out)}")
    typer.echo(f"Accept: {audit.summary.accept}")
    typer.echo(f"Review: {audit.summary.review}")
    typer.echo(f"Reject: {audit.summary.reject}")
    if fail_on == "review" and (audit.summary.review or audit.summary.reject):
        raise typer.Exit(1)
    if fail_on == "reject" and audit.summary.reject:
        raise typer.Exit(1)


@leaderboard_app.command("inspect")
def leaderboard_inspect(
    submission_file: Path,
    verify_artifacts: bool = LEADERBOARD_VERIFY_ARTIFACTS_OPTION,
    verify_github_run: bool = LEADERBOARD_VERIFY_GITHUB_RUN_OPTION,
    out: Path | None = LEADERBOARD_INSPECT_OUT_OPTION,
) -> None:
    try:
        inspection = inspect_leaderboard_submission(
            submission_file,
            verify_artifacts=verify_artifacts,
            verify_github_run=verify_github_run,
        )
    except LeaderboardValidationError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(inspection.markdown, encoding="utf-8")
        typer.echo(f"Wrote leaderboard inspection: {_display_path(out)}")
        typer.echo(f"Artifact hashes: {inspection.artifact_status}")
        typer.echo(f"GitHub run: {inspection.github_run_status}")
        typer.echo(f"Warnings: {inspection.warning_count}")
        return

    typer.echo(inspection.markdown)


@leaderboard_app.command("reproduce")
def leaderboard_reproduce(
    submission_file: Path,
    out: Path = LEADERBOARD_REPRODUCE_OUT_OPTION,
) -> None:
    try:
        script = generate_leaderboard_reproduction_script(
            submission_file,
            out_path=out,
        )
    except LeaderboardValidationError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    typer.echo(f"Wrote leaderboard reproduction script: {_display_path(script.path)}")
    typer.echo("Review before executing; the script clones and runs the submitted agent repo.")


@leaderboard_app.command("build")
def leaderboard_build(
    submissions_dir: Path,
    out: Path = LEADERBOARD_INDEX_OUT_OPTION,
    json_out: Path = LEADERBOARD_INDEX_JSON_OUT_OPTION,
    verify_artifacts: bool = LEADERBOARD_BUILD_VERIFY_ARTIFACTS_OPTION,
    require_trust_level: str | None = LEADERBOARD_REQUIRE_TRUST_OPTION,
    verify_github_run: bool = LEADERBOARD_VERIFY_GITHUB_RUN_OPTION,
) -> None:
    try:
        index = build_leaderboard_index(
            submissions_dir,
            csv_path=out,
            json_path=json_out,
            verify_artifacts=verify_artifacts,
            require_trust_level=require_trust_level,
            verify_github_run=verify_github_run,
        )
    except LeaderboardValidationError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Wrote leaderboard CSV: {_display_path(out)}")
    typer.echo(f"Wrote leaderboard JSON: {_display_path(json_out)}")
    typer.echo(f"Rows: {len(index.rows)}")


@leaderboard_app.command("pr")
def leaderboard_pr(
    submission_file: Path,
    leaderboard_repo: Path = LEADERBOARD_REPO_OPTION,
    submission_name: str | None = LEADERBOARD_SUBMISSION_NAME_OPTION,
    pr_body_out: Path | None = LEADERBOARD_PR_BODY_OUT_OPTION,
    force: bool = LEADERBOARD_FORCE_OPTION,
    require_trust_level: str | None = LEADERBOARD_REQUIRE_TRUST_OPTION,
    verify_github_run: bool = LEADERBOARD_VERIFY_GITHUB_RUN_OPTION,
) -> None:
    try:
        prepared = prepare_leaderboard_pr_submission(
            submission_path=submission_file,
            leaderboard_repo=leaderboard_repo,
            submission_name=submission_name,
            pr_body_out=pr_body_out,
            force=force,
            require_trust_level=require_trust_level,
            verify_github_run=verify_github_run,
        )
    except LeaderboardValidationError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    typer.echo(f"Prepared leaderboard PR file: {_display_path(prepared.target_path)}")
    if pr_body_out is not None:
        typer.echo(f"Wrote leaderboard PR body: {_display_path(pr_body_out)}")
    typer.echo(f"Trust level: {prepared.submission.verification.trust_level}")
    typer.echo(f"Evidence SHA-256: {prepared.submission.verification.evidence_sha256}")
    typer.echo("Next steps:")
    typer.echo(prepared.next_steps)


@app.command()
def report(run_dir: Path) -> None:
    with _handle_results_artifact_errors():
        report_path = regenerate_report(run_dir)
    typer.echo(f"Regenerated {report_path}")


@app.command()
def repair(run_dir: Path) -> None:
    with _handle_results_artifact_errors():
        repair_path = generate_repair_plan(run_dir)
    typer.echo(f"Wrote {repair_path}")


@app.command()
def fix(
    run_dir: Path,
    out: Path = FIX_OUT_OPTION,
    prompt: Path | None = FIX_PROMPT_OPTION,
    tools: Path | None = FIX_TOOLS_OPTION,
) -> None:
    with _handle_results_artifact_errors():
        patch_path = generate_fix_patch(
            run_dir,
            prompt_path=prompt,
            tools_path=tools,
            out_path=out,
        )
    typer.echo(f"Wrote {patch_path}")


@app.command()
def learn(
    trace_file: str,
    jsonl_file: Path | None = LEARN_JSONL_FILE_ARGUMENT,
    out: Path = LEARN_OUT_OPTION,
    name: str = typer.Option("learned_regression_suite", "--name", help="Generated suite name."),
    scenario_id: str | None = typer.Option(None, "--scenario-id", help="Generated scenario id."),
    user_input: str | None = typer.Option(None, "--input", help="Original user input for JSONL."),
    runs_dir: Path = LEARN_JSONL_RUNS_DIR_OPTION,
) -> None:
    if trace_file == "jsonl":
        if jsonl_file is None:
            typer.echo("JSONL source file is required.", err=True)
            raise typer.Exit(2)
        if scenario_id is None:
            typer.echo("--scenario-id is required when learning from JSONL.", err=True)
            raise typer.Exit(2)
        if user_input is None:
            typer.echo("--input is required when learning from JSONL.", err=True)
            raise typer.Exit(2)
        try:
            imported_trace_path = ingest_jsonl_trace(
                jsonl_file,
                out_dir=runs_dir,
                scenario_id=scenario_id,
                user_input=user_input,
            )
        except ValueError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(1) from error
        with _handle_trace_artifact_errors():
            trace = load_trace(imported_trace_path)
        learned_path = write_learned_scenario(
            trace,
            out_path=out,
            trace_path=imported_trace_path,
            suite_name=name,
            scenario_id=scenario_id,
        )
        typer.echo(f"Wrote {imported_trace_path}")
        typer.echo(f"Wrote {learned_path}")
        return

    trace_path = Path(trace_file)
    with _handle_trace_artifact_errors():
        trace = load_trace(trace_path)
    learned_path = write_learned_scenario(
        trace,
        out_path=out,
        trace_path=trace_path,
        suite_name=name,
        scenario_id=scenario_id,
    )
    typer.echo(f"Wrote {learned_path}")


@app.command()
def summary(run_dir: Path, github: bool = GITHUB_SUMMARY_OPTION) -> None:
    if not github:
        typer.echo("Rendering GitHub-compatible Markdown summary.", err=True)
    with _handle_results_artifact_errors():
        typer.echo(generate_github_summary(run_dir), nl=False)


@app.command("pr-comment")
def pr_comment(
    run_dir: Path,
    out: Path = PR_COMMENT_OUT_OPTION,
    compare: Path | None = PR_COMMENT_COMPARE_OPTION,
) -> None:
    with _handle_results_artifact_errors():
        comment_path = write_pr_comment(run_dir, out_path=out, compare_path=compare)
    typer.echo(f"Wrote {comment_path}")


@app.command()
def fuzz(
    scenario_file: Path,
    out: Path = FUZZ_OUT_OPTION,
    mutations: int = FUZZ_MUTATIONS_OPTION,
    focus: str = FUZZ_FOCUS_OPTION,
) -> None:
    fuzzed_path = fuzz_scenario_file(
        scenario_file,
        out_path=out,
        mutations=mutations,
        focus=focus,
    )
    typer.echo(f"Wrote {fuzzed_path}")


@app.command()
def compare(
    baseline_dir: Path,
    latest_dir: Path,
    json_output: bool = COMPARE_JSON_OPTION,
    out: Path | None = COMPARE_OUT_OPTION,
) -> None:
    with _handle_results_artifact_errors():
        result = compare_runs(baseline_dir, latest_dir)
    json_payload = json.dumps(compare_result_payload(result), indent=2, sort_keys=True)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"{json_payload}\n", encoding="utf-8")

    if json_output:
        typer.echo(json_payload)
        return

    typer.echo(f"Baseline pass rate: {result.baseline_pass_rate:.1f}%")
    typer.echo(f"Latest pass rate: {result.latest_pass_rate:.1f}%")
    typer.echo(f"Delta: {result.delta:+.1f}%")
    _print_failure_deltas("New failures", result.new_failures)
    _print_failure_deltas("Resolved failures", result.resolved_failures)
    _print_flaky_scenario_deltas("New flaky scenarios", result.new_flaky_scenarios)
    _print_flaky_scenario_deltas(
        "Resolved flaky scenarios",
        result.resolved_flaky_scenarios,
    )

    if result.severity_changes:
        typer.echo("Severity changes:")
        for change in result.severity_changes:
            typer.echo(
                f"- {change.failure_type}: {change.baseline_severity} -> {change.latest_severity}"
            )
    else:
        typer.echo("Severity changes: none")

    if result.scenario_regressions:
        typer.echo("Scenario regressions:")
        for regression in result.scenario_regressions:
            typer.echo(
                f"- {regression.scenario_id}: {regression.baseline_pass_rate:.1f}% -> "
                f"{regression.latest_pass_rate:.1f}% ({regression.delta:+.1f}%)"
            )
    else:
        typer.echo("Scenario regressions: none")

    if result.scenario_improvements:
        typer.echo("Scenario improvements:")
        for improvement in result.scenario_improvements:
            typer.echo(
                f"- {improvement.scenario_id}: {improvement.baseline_pass_rate:.1f}% -> "
                f"{improvement.latest_pass_rate:.1f}% ({improvement.delta:+.1f}%)"
            )
    else:
        typer.echo("Scenario improvements: none")

    if out is not None:
        typer.echo(f"Wrote {out}")


@mcp_app.command("audit")
def mcp_audit(
    tools_file: Path,
    out: Path = LEARN_OUT_OPTION,
    report_path: Path = MCP_REPORT_OPTION,
) -> None:
    result = audit_mcp_tools(load_mcp_tools(tools_file), out_path=out, report_path=report_path)
    typer.echo(f"Wrote {result.scenario_path}")
    typer.echo(f"Wrote {result.report_path}")


@mcp_app.command("snapshot")
def mcp_snapshot(
    command: str | None = MCP_COMMAND_OPTION,
    command_json: str | None = MCP_COMMAND_JSON_OPTION,
    out: Path = MCP_SNAPSHOT_OUT_OPTION,
    audit_out: Path | None = MCP_AUDIT_OUT_OPTION,
    report_path: Path | None = MCP_SNAPSHOT_REPORT_OPTION,
    timeout_seconds: float = MCP_TIMEOUT_OPTION,
) -> None:
    try:
        tools = snapshot_mcp_tools(
            _select_mcp_command(command, command_json),
            out_path=out,
            timeout_seconds=timeout_seconds,
        )
        typer.echo(f"Wrote {out}")
        if audit_out is not None:
            if report_path is None:
                typer.echo("--report is required when --audit-out is provided.", err=True)
                raise typer.Exit(2)
            result = audit_mcp_tools(tools, out_path=audit_out, report_path=report_path)
            typer.echo(f"Wrote {result.scenario_path}")
            typer.echo(f"Wrote {result.report_path}")
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error


@mcp_app.command("repair")
def mcp_repair(
    tools_file: Path,
    out: Path = MCP_REPAIR_OUT_OPTION,
    offline: bool = OFFLINE_OPTION,
    redact: bool | None = REDACT_OPTION,
) -> None:
    try:
        result = generate_mcp_repair(
            load_mcp_tools(tools_file),
            out_path=out,
            offline=offline,
            redact=redact,
        )
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Wrote {result.report_path}")


@mcp_app.command("harden")
def mcp_harden(
    command: str | None = MCP_COMMAND_OPTION,
    command_json: str | None = MCP_COMMAND_JSON_OPTION,
    snapshot_out: Path = MCP_HARDEN_SNAPSHOT_OUT_OPTION,
    audit_out: Path = MCP_HARDEN_AUDIT_OUT_OPTION,
    audit_report: Path = MCP_HARDEN_AUDIT_REPORT_OPTION,
    repair_out: Path = MCP_HARDEN_REPAIR_OUT_OPTION,
    timeout_seconds: float = MCP_TIMEOUT_OPTION,
    offline: bool = OFFLINE_OPTION,
    redact: bool | None = REDACT_OPTION,
    github_summary: bool = MCP_HARDEN_GITHUB_SUMMARY_OPTION,
) -> None:
    try:
        result = harden_mcp_server(
            _select_mcp_command(command, command_json),
            snapshot_path=snapshot_out,
            audit_out_path=audit_out,
            audit_report_path=audit_report,
            repair_out_path=repair_out,
            timeout_seconds=timeout_seconds,
            offline=offline,
            redact=redact,
        )
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Wrote {result.snapshot_path}")
    typer.echo(f"Wrote {result.audit_result.scenario_path}")
    typer.echo(f"Wrote {result.audit_result.report_path}")
    typer.echo(f"Wrote {result.repair_result.report_path}")
    if github_summary:
        _write_github_summary(render_mcp_harden_summary(result))


def _select_mcp_command(command: str | None, command_json: str | None) -> str | list[str]:
    if command and command_json:
        raise ValueError("Use either --command or --command-json, not both.")
    if command_json:
        try:
            payload = json.loads(command_json)
        except json.JSONDecodeError as error:
            raise ValueError(f"--command-json must be a JSON array: {error.msg}") from error
        if not isinstance(payload, list) or not payload:
            raise ValueError("--command-json must be a non-empty JSON array.")
        if not all(isinstance(part, str) and part for part in payload):
            raise ValueError("--command-json entries must be non-empty strings.")
        return payload
    if command:
        return command
    raise ValueError("Either --command or --command-json is required.")


def _write_github_summary(markdown: str) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        typer.echo(markdown, nl=False)
        return
    with Path(summary_path).open("a", encoding="utf-8") as summary_file:
        summary_file.write(markdown)
        if not markdown.endswith("\n"):
            summary_file.write("\n")


@trace_app.command("export")
def trace_export(
    run_dir: Path,
    out: Path = TRACE_EXPORT_OUT_OPTION,
    trace_format: str = TRACE_FORMAT_OPTION,
) -> None:
    if trace_format != "openai-trace":
        typer.echo("Only --format openai-trace is supported.", err=True)
        raise typer.Exit(2)
    with _handle_trace_artifact_errors():
        output_path = export_openai_trace(run_dir, out_path=out)
    typer.echo(f"Wrote {output_path}")


@trace_app.command("import")
def trace_import(
    source_file: Path,
    out: Path = TRACE_IMPORT_OUT_OPTION,
    trace_format: str = TRACE_FORMAT_OPTION,
) -> None:
    if trace_format != "openai-trace":
        typer.echo("Only --format openai-trace is supported.", err=True)
        raise typer.Exit(2)
    with _handle_openai_trace_payload_errors():
        traces = import_openai_trace(source_file, out_dir=out)
    typer.echo(f"Wrote {out / 'traces'} ({len(traces)} traces)")


@ingest_app.command("jsonl")
def ingest_jsonl(
    source_file: Path,
    scenario_id: str = INGEST_SCENARIO_ID_OPTION,
    user_input: str = INGEST_INPUT_OPTION,
    out: Path = INGEST_OUT_OPTION,
    trial: int = INGEST_TRIAL_OPTION,
) -> None:
    try:
        trace_path = ingest_jsonl_trace(
            source_file,
            out_dir=out,
            scenario_id=scenario_id,
            user_input=user_input,
            trial=trial,
        )
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Wrote {trace_path}")


def _print_failure_deltas(title: str, deltas: list[FailureDelta]) -> None:
    if not deltas:
        typer.echo(f"{title}: none")
        return
    typer.echo(f"{title}:")
    for delta in deltas:
        typer.echo(
            f"- {delta.failure_type} / {delta.severity}: "
            f"{delta.baseline_count} -> {delta.latest_count}"
        )


def _print_flaky_scenario_deltas(title: str, scenarios: list[FlakyScenario]) -> None:
    if not scenarios:
        typer.echo(f"{title}: none")
        return
    typer.echo(f"{title}:")
    for scenario in scenarios:
        typer.echo(
            f"- {scenario.scenario_id}: {scenario.passed_trials}/{scenario.total_trials} "
            f"trials passed ({scenario.pass_rate:.1f}%)"
        )


def _run_command(
    *,
    scenario_file: Path,
    runs_dir: Path,
    trials: int | None,
    offline: bool,
    redact: bool | None,
    agent_mode: str | None,
    failed: bool,
) -> str:
    parts = ["uv", "run", "anvil", "run", str(_display_path(scenario_file))]
    if runs_dir != Path("runs"):
        parts.extend(["--runs-dir", str(_display_path(runs_dir))])
    if offline:
        parts.append("--offline")
    if redact is True:
        parts.append("--redact")
    elif redact is False:
        parts.append("--no-redact")
    if agent_mode:
        parts.extend(["--agent-mode", agent_mode])
    if trials is not None:
        parts.extend(["--trials", str(trials)])
    command = " ".join(parts)
    if failed:
        command += " || true"
    return command


def _display_path(path: Path) -> Path:
    try:
        return path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return path


if __name__ == "__main__":
    app()
