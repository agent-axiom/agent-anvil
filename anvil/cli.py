from __future__ import annotations

from pathlib import Path

import typer

from anvil.fix import generate_fix_patch
from anvil.fuzzing import fuzz_scenario_file
from anvil.learning import load_trace, write_learned_scenario
from anvil.mcp_audit import audit_mcp_tools, load_mcp_tools
from anvil.pr_comment import write_pr_comment
from anvil.repair import generate_repair_plan
from anvil.runner import (
    FailureDelta,
    OpenAIKeyMissingError,
    compare_runs,
    default_semantic_grader,
    regenerate_report,
    run_suite,
)
from anvil.summary import generate_github_summary
from anvil.terminal import print_run_summary
from anvil.trace_bridge import export_openai_trace, import_openai_trace

app = typer.Typer(help="Agent Anvil CI-first eval harness.")
mcp_app = typer.Typer(help="Audit MCP tools and generate safety scenarios.")
trace_app = typer.Typer(help="Import and export trace formats.")
app.add_typer(mcp_app, name="mcp")
app.add_typer(trace_app, name="trace")
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
AGENT_MODE_OPTION = typer.Option(
    None,
    "--agent-mode",
    help="Agent execution mode for demo agents: offline, openai, or auto.",
)
LEARN_OUT_OPTION = typer.Option(..., "--out", help="Write the learned scenario YAML here.")
FIX_OUT_OPTION = typer.Option(..., "--out", help="Write the generated patch diff here.")
MCP_REPORT_OPTION = typer.Option(..., "--report", help="Write the MCP audit Markdown report here.")
TRACE_FORMAT_OPTION = typer.Option("openai-trace", "--format", help="Trace format.")
FIX_PROMPT_OPTION = typer.Option(None, "--prompt", help="Prompt file to patch in the diff.")
FIX_TOOLS_OPTION = typer.Option(None, "--tools", help="Tool definition file to patch in the diff.")
TRACE_EXPORT_OUT_OPTION = typer.Option(..., "--out", help="Write exported trace JSON here.")
TRACE_IMPORT_OUT_OPTION = typer.Option(..., "--out", help="Write imported Anvil trace run here.")
FUZZ_OUT_OPTION = typer.Option(..., "--out", help="Write the fuzzed scenario YAML here.")
FUZZ_MUTATIONS_OPTION = typer.Option(10, "--mutations", min=1, help="Number of mutations.")
FUZZ_FOCUS_OPTION = typer.Option("tool_safety", "--focus", help="Mutation focus.")
PR_COMMENT_OUT_OPTION = typer.Option(..., "--out", help="Write PR-ready Markdown here.")


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
def report(run_dir: Path) -> None:
    report_path = regenerate_report(run_dir)
    typer.echo(f"Regenerated {report_path}")


@app.command()
def repair(run_dir: Path) -> None:
    repair_path = generate_repair_plan(run_dir)
    typer.echo(f"Wrote {repair_path}")


@app.command()
def fix(
    run_dir: Path,
    out: Path = FIX_OUT_OPTION,
    prompt: Path | None = FIX_PROMPT_OPTION,
    tools: Path | None = FIX_TOOLS_OPTION,
) -> None:
    patch_path = generate_fix_patch(run_dir, prompt_path=prompt, tools_path=tools, out_path=out)
    typer.echo(f"Wrote {patch_path}")


@app.command()
def learn(
    trace_file: Path,
    out: Path = LEARN_OUT_OPTION,
    name: str = typer.Option("learned_regression_suite", "--name", help="Generated suite name."),
    scenario_id: str | None = typer.Option(None, "--scenario-id", help="Generated scenario id."),
) -> None:
    trace = load_trace(trace_file)
    learned_path = write_learned_scenario(
        trace,
        out_path=out,
        trace_path=trace_file,
        suite_name=name,
        scenario_id=scenario_id,
    )
    typer.echo(f"Wrote {learned_path}")


@app.command()
def summary(run_dir: Path, github: bool = GITHUB_SUMMARY_OPTION) -> None:
    if not github:
        typer.echo("Rendering GitHub-compatible Markdown summary.", err=True)
    typer.echo(generate_github_summary(run_dir), nl=False)


@app.command("pr-comment")
def pr_comment(run_dir: Path, out: Path = PR_COMMENT_OUT_OPTION) -> None:
    comment_path = write_pr_comment(run_dir, out_path=out)
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
def compare(baseline_dir: Path, latest_dir: Path) -> None:
    result = compare_runs(baseline_dir, latest_dir)
    typer.echo(f"Baseline pass rate: {result.baseline_pass_rate:.1f}%")
    typer.echo(f"Latest pass rate: {result.latest_pass_rate:.1f}%")
    typer.echo(f"Delta: {result.delta:+.1f}%")
    _print_failure_deltas("New failures", result.new_failures)
    _print_failure_deltas("Resolved failures", result.resolved_failures)

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


@mcp_app.command("audit")
def mcp_audit(
    tools_file: Path,
    out: Path = LEARN_OUT_OPTION,
    report_path: Path = MCP_REPORT_OPTION,
) -> None:
    result = audit_mcp_tools(load_mcp_tools(tools_file), out_path=out, report_path=report_path)
    typer.echo(f"Wrote {result.scenario_path}")
    typer.echo(f"Wrote {result.report_path}")


@trace_app.command("export")
def trace_export(
    run_dir: Path,
    out: Path = TRACE_EXPORT_OUT_OPTION,
    trace_format: str = TRACE_FORMAT_OPTION,
) -> None:
    if trace_format != "openai-trace":
        typer.echo("Only --format openai-trace is supported.", err=True)
        raise typer.Exit(2)
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
    traces = import_openai_trace(source_file, out_dir=out)
    typer.echo(f"Wrote {out / 'traces'} ({len(traces)} traces)")


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
        return path.relative_to(Path.cwd())
    except ValueError:
        return path


if __name__ == "__main__":
    app()
