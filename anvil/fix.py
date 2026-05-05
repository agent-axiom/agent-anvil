from __future__ import annotations

import difflib
from pathlib import Path

from anvil.storage import load_results

WEAK_REFUND_DESCRIPTION = "Issues a refund to a customer."
SAFE_REFUND_DESCRIPTION = (
    "Only call after lookup_order confirms the order exists, belongs to the customer, "
    "and is eligible for refund."
)
PROMPT_GUARDRAIL = (
    "Before calling destructive tools such as issue_refund, verify required identifiers "
    "and eligibility with lookup tools."
)


def generate_fix_patch(
    run_dir: str | Path,
    *,
    prompt_path: str | Path | None = None,
    tools_path: str | Path | None = None,
    out_path: str | Path,
) -> Path:
    payload = load_results(run_dir)
    patch_parts: list[str] = []
    if _has_premature_tool_failure(payload):
        if prompt_path is not None:
            patch_parts.append(_prompt_patch(Path(prompt_path)))
        if tools_path is not None:
            patch_parts.append(_tools_patch(Path(tools_path)))

    patch_text = "".join(part for part in patch_parts if part)
    if not patch_text:
        patch_text = "# Agent Anvil generated no patch suggestions for this run.\n"

    selected_path = Path(out_path)
    selected_path.parent.mkdir(parents=True, exist_ok=True)
    selected_path.write_text(patch_text, encoding="utf-8")
    return selected_path


def _has_premature_tool_failure(payload: dict[str, object]) -> bool:
    clusters = payload.get("clusters", [])
    if not isinstance(clusters, list):
        return False
    return any(
        isinstance(cluster, dict) and cluster.get("name") == "premature_tool_execution"
        for cluster in clusters
    )


def _prompt_patch(path: Path) -> str:
    original = path.read_text(encoding="utf-8")
    updated = original.replace(WEAK_REFUND_DESCRIPTION, SAFE_REFUND_DESCRIPTION)
    if PROMPT_GUARDRAIL not in updated:
        updated = updated.rstrip() + "\n\n" + PROMPT_GUARDRAIL + "\n"
    if updated == original:
        return ""
    return _unified_diff(path, original, updated)


def _tools_patch(path: Path) -> str:
    original = path.read_text(encoding="utf-8")
    updated = original.replace(WEAK_REFUND_DESCRIPTION, SAFE_REFUND_DESCRIPTION)
    if updated == original:
        return ""
    return _unified_diff(path, original, updated)


def _unified_diff(path: Path, original: str, updated: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
    )
