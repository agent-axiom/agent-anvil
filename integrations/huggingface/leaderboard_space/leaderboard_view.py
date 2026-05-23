from __future__ import annotations

from collections import Counter
from typing import Any

TRUST_BADGES = {
    "self_reported": "[self-reported]",
    "github_actions": "[GitHub Actions]",
    "maintainer_rerun": "[maintainer rerun]",
}

TRUST_LABELS = {
    "self_reported": "self-reported",
    "github_actions": "GitHub Actions",
    "maintainer_rerun": "maintainer rerun",
}

DISPLAY_COLUMNS = [
    "rank",
    "agent_name",
    "agent_version",
    "trust_badge",
    "trace_aware_pass_rate",
    "final_answer_pass_rate",
    "answer_only_missed_failures",
    "answer_only_missed_failure_rate",
    "total_trials",
    "repo_url",
    "github_run_url",
    "maintainer_rerun_url",
    "evidence_sha256",
]

ALL_COLUMNS = [
    *DISPLAY_COLUMNS,
    "benchmark_name",
    "trust_level",
    "commit_sha",
    "maintainer",
    "maintainer_rerun_repository",
    "maintainer_rerun_sha",
]

SORT_COLUMNS = {
    "trace_aware_pass_rate",
    "final_answer_pass_rate",
    "answer_only_missed_failures",
    "answer_only_missed_failure_rate",
    "total_trials",
    "rank",
}


def normalize_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_rows = payload.get("rows", [])
    if not isinstance(raw_rows, list):
        raw_rows = []

    rows: list[dict[str, Any]] = []
    for index, raw_row in enumerate(raw_rows, start=1):
        row = dict(raw_row) if isinstance(raw_row, dict) else {}
        for column in ALL_COLUMNS:
            row.setdefault(column, "")
        row["rank"] = _int_or_default(row.get("rank"), index)
        row["trust_badge"] = TRUST_BADGES.get(
            str(row.get("trust_level") or ""),
            str(row.get("trust_level") or ""),
        )
        for column in SORT_COLUMNS:
            if column != "rank":
                row[column] = _float_or_default(row.get(column), 0.0)
        rows.append(row)
    return rows


def filter_rows(
    rows: list[dict[str, Any]],
    *,
    search: str,
    trust_level: str,
    min_trials: int | float,
    sort_by: str,
    descending: bool,
) -> list[dict[str, Any]]:
    needle = search.strip().lower()
    trusted = trust_level.strip()
    minimum_trials = _float_or_default(min_trials, 0.0)

    filtered = [
        row
        for row in rows
        if _matches_search(row, needle)
        and _matches_trust(row, trusted)
        and _float_or_default(row.get("total_trials"), 0.0) >= minimum_trials
    ]
    sort_column = sort_by if sort_by in SORT_COLUMNS else "trace_aware_pass_rate"
    return sorted(
        filtered,
        key=lambda row: _float_or_default(row.get(sort_column), 0.0),
        reverse=descending,
    )


def table_values(rows: list[dict[str, Any]]) -> list[list[Any]]:
    return [[row.get(column, "") for column in DISPLAY_COLUMNS] for row in rows]


def summary_markdown(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "### Snapshot\n\nRows: 0\n\nNo matching leaderboard rows."

    best_trace = max(_float_or_default(row.get("trace_aware_pass_rate"), 0.0) for row in rows)
    missed_failures = sum(
        int(_float_or_default(row.get("answer_only_missed_failures"), 0.0)) for row in rows
    )
    trust_counts = Counter(str(row.get("trust_level") or "") for row in rows)
    trust_mix = ", ".join(
        f"{TRUST_LABELS.get(level, level or 'unknown')}: {count}"
        for level, count in sorted(trust_counts.items())
    )

    return "\n".join(
        [
            "### Snapshot",
            "",
            f"Rows: {len(rows)}",
            f"Best trace-aware pass rate: {best_trace:.1f}%",
            f"Answer-only missed failures: {missed_failures}",
            f"Trust mix: {trust_mix}",
        ]
    )


def _matches_search(row: dict[str, Any], needle: str) -> bool:
    if not needle:
        return True
    haystack = " ".join(
        str(row.get(column, ""))
        for column in ("agent_name", "agent_version", "repo_url", "benchmark_name")
    ).lower()
    return needle in haystack


def _matches_trust(row: dict[str, Any], trust_level: str) -> bool:
    return trust_level in {"", "all"} or str(row.get("trust_level") or "") == trust_level


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
