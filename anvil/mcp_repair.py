from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from openai import OpenAI
from pydantic import BaseModel

from anvil.config import DEFAULT_OPENAI_MODEL, AnvilSettings
from anvil.mcp_audit import (
    McpCommand,
    ToolAuditFinding,
    ToolAuditResult,
    audit_mcp_tools,
    find_mcp_tool_findings,
    snapshot_mcp_tools,
)
from anvil.redaction import redact_payload

MCP_REDACTION_PATTERNS = [r"\btenant-[A-Za-z0-9_-]+\b"]


class McpRepairPatch(BaseModel):
    tool_name: str
    current_description: str
    suggested_description: str
    rationale: str
    policy_patch: list[str]
    scenario_patch: list[str]


class McpRepairPlan(BaseModel):
    summary: str
    patches: list[McpRepairPatch]


class McpRepairer(Protocol):
    def repair(self, tools: list[dict[str, Any]]) -> McpRepairPlan: ...


@dataclass(frozen=True)
class McpRepairResult:
    plan: McpRepairPlan
    report_path: Path


@dataclass(frozen=True)
class McpHardenResult:
    snapshot_path: Path
    audit_result: ToolAuditResult
    repair_result: McpRepairResult


class OfflineMcpRepairer:
    def repair(self, tools: list[dict[str, Any]]) -> McpRepairPlan:
        findings = find_mcp_tool_findings(tools)
        patches = [
            _offline_patch(tool, _findings_for_tool(findings, str(tool.get("name", ""))))
            for tool in tools
            if _findings_for_tool(findings, str(tool.get("name", "")))
        ]
        if not patches:
            return McpRepairPlan(
                summary="No MCP tool repair suggestions were generated.",
                patches=[],
            )
        return McpRepairPlan(
            summary=(
                "MCP tools need clearer safety preconditions, argument descriptions, "
                "and regression scenarios before agents use them."
            ),
            patches=patches,
        )


class OpenAIMcpRepairer:
    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str = DEFAULT_OPENAI_MODEL,
        redact: bool = True,
        redaction_patterns: list[str] | None = None,
    ) -> None:
        if client is None:
            client = OpenAI()
        self.client = client
        self.model = model
        self.redact = redact
        self.redaction_patterns = [*MCP_REDACTION_PATTERNS, *(redaction_patterns or [])]

    def repair(self, tools: list[dict[str, Any]]) -> McpRepairPlan:
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are Agent Anvil's MCP tool repair assistant. Return a strict "
                        "structured repair plan for MCP tool schemas before they are handed to "
                        "tool-using agents. Focus on destructive tools, missing verification "
                        "preconditions, vague descriptions, missing argument descriptions, tenant "
                        "boundaries, approval requirements, and regression scenarios. Suggested "
                        "descriptions must be concrete and safe to paste into tool metadata."
                    ),
                },
                {"role": "user", "content": _repair_payload(tools, redacter=self)},
            ],
            text_format=McpRepairPlan,
        )
        return McpRepairPlan.model_validate(response.output_parsed)


def generate_mcp_repair(
    tools: list[dict[str, Any]],
    *,
    out_path: str | Path,
    offline: bool = False,
    repairer: McpRepairer | None = None,
    redact: bool | None = None,
) -> McpRepairResult:
    selected_repairer = repairer or _default_repairer(offline=offline, redact=redact)
    plan = selected_repairer.repair(tools)
    selected_out_path = Path(out_path)
    selected_out_path.parent.mkdir(parents=True, exist_ok=True)
    selected_out_path.write_text(render_mcp_repair_markdown(plan), encoding="utf-8")
    return McpRepairResult(plan=plan, report_path=selected_out_path)


def harden_mcp_server(
    command: McpCommand,
    *,
    snapshot_path: str | Path,
    audit_out_path: str | Path,
    audit_report_path: str | Path,
    repair_out_path: str | Path,
    timeout_seconds: float = 10.0,
    offline: bool = False,
    redact: bool | None = None,
) -> McpHardenResult:
    tools = snapshot_mcp_tools(command, out_path=snapshot_path, timeout_seconds=timeout_seconds)
    audit_result = audit_mcp_tools(
        tools,
        out_path=audit_out_path,
        report_path=audit_report_path,
    )
    repair_result = generate_mcp_repair(
        tools,
        out_path=repair_out_path,
        offline=offline,
        redact=redact,
    )
    return McpHardenResult(
        snapshot_path=Path(snapshot_path),
        audit_result=audit_result,
        repair_result=repair_result,
    )


def render_mcp_harden_summary(result: McpHardenResult) -> str:
    findings = result.audit_result.findings
    risky_tools = sorted({finding.tool_name for finding in findings})
    repair_tools = [patch.tool_name for patch in result.repair_result.plan.patches]
    lines = [
        "# Agent Anvil MCP Harden",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Risky tools | {len(risky_tools)} |",
        f"| Audit findings | {len(findings)} |",
        f"| Repair patches | {len(repair_tools)} |",
        "",
    ]
    if risky_tools:
        lines.extend(["## Risky Tools", ""])
        lines.extend(f"- `{tool}`" for tool in risky_tools)
        lines.append("")
    if repair_tools:
        lines.extend(["## Repair Targets", ""])
        lines.extend(f"- `{tool}`" for tool in repair_tools)
        lines.append("")
    lines.extend(
        [
            "## Artifacts",
            "",
            f"- Snapshot: `{result.snapshot_path}`",
            f"- Generated scenarios: `{result.audit_result.scenario_path}`",
            f"- Audit report: `{result.audit_result.report_path}`",
            f"- Repair plan: `{result.repair_result.report_path}`",
            "",
        ]
    )
    return "\n".join(lines)


def render_mcp_repair_markdown(plan: McpRepairPlan) -> str:
    lines = ["# MCP Tool Repair Plan", "", plan.summary, ""]
    if not plan.patches:
        lines.extend(["No MCP tool repairs suggested.", ""])
        return "\n".join(lines)

    lines.extend(["## Tool description patches", ""])
    for patch in plan.patches:
        lines.extend(
            [
                f"### `{patch.tool_name}`",
                "",
                "**Current description**",
                "",
                patch.current_description or "_No description provided._",
                "",
                "**Suggested description**",
                "",
                patch.suggested_description,
                "",
                f"**Rationale:** {patch.rationale}",
                "",
            ]
        )
        if patch.policy_patch:
            lines.extend(["**Policy patch**", ""])
            lines.extend(f"- {item}" for item in patch.policy_patch)
            lines.append("")
        if patch.scenario_patch:
            lines.extend(["**Scenario patch**", ""])
            lines.extend(f"- {item}" for item in patch.scenario_patch)
            lines.append("")
    return "\n".join(lines)


def _default_repairer(*, offline: bool, redact: bool | None) -> McpRepairer:
    if offline or AnvilSettings.from_env().offline:
        return OfflineMcpRepairer()
    if not os.getenv("OPENAI_API_KEY"):
        msg = (
            "OPENAI_API_KEY is required for OpenAI MCP repair. "
            "Set OPENAI_API_KEY or run with --offline/ANVIL_OFFLINE=true "
            "to use local MCP repair hints."
        )
        raise ValueError(msg)
    settings = AnvilSettings.from_env()
    return OpenAIMcpRepairer(
        model=settings.openai_model,
        redact=settings.redact if redact is None else redact,
        redaction_patterns=settings.redaction_patterns,
    )


def _repair_payload(tools: list[dict[str, Any]], *, redacter: OpenAIMcpRepairer) -> str:
    findings = [finding.__dict__ for finding in find_mcp_tool_findings(tools)]
    payload: Any = {"tools": tools, "findings": findings}
    if redacter.redact:
        payload = redact_payload(payload, patterns=redacter.redaction_patterns)
    return (
        "MCP tool schemas and local audit findings:\n"
        f"{json.dumps(payload, indent=2)}\n\n"
        "Generate repair suggestions that improve tool descriptions and add scenario/policy "
        "checks for unsafe agent behavior."
    )


def _offline_patch(tool: dict[str, Any], findings: list[ToolAuditFinding]) -> McpRepairPatch:
    tool_name = str(tool.get("name", ""))
    current_description = str(tool.get("description", ""))
    missing_arguments = [
        finding.detail.removeprefix("missing argument description: ")
        for finding in findings
        if finding.smell == "missing_argument_description"
    ]
    policy_patch = [
        f"Add `{tool_name}` to destructive_tools.",
        f"Add a required prior verification policy for `{tool_name}`.",
    ]
    scenario_patch = [
        f"Add a scenario where `{tool_name}` is requested without verified identifiers.",
        f"Assert the agent asks for clarification instead of calling `{tool_name}`.",
    ]
    scenario_patch.extend(
        f"Document `{argument}` in the tool schema." for argument in missing_arguments
    )
    return McpRepairPatch(
        tool_name=tool_name,
        current_description=current_description,
        suggested_description=(
            f"Only call `{tool_name}` after verification confirms required identifiers, "
            "authorization, tenant ownership, eligibility, and human approval for destructive "
            "actions. If verification is missing or ambiguous, ask for clarification instead."
        ),
        rationale=(
            "Agents rely on tool metadata when deciding whether a call is safe. Destructive MCP "
            "tools need explicit preconditions and argument semantics."
        ),
        policy_patch=policy_patch,
        scenario_patch=scenario_patch,
    )


def _findings_for_tool(findings: list[ToolAuditFinding], tool_name: str) -> list[ToolAuditFinding]:
    return [finding for finding in findings if finding.tool_name == tool_name]
