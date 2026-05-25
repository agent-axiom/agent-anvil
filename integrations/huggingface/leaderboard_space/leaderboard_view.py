from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
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
    "freshness_badge",
    "compatibility_badge",
    "health_badge",
    "trace_aware_pass_rate",
    "final_answer_pass_rate",
    "answer_only_missed_failures",
    "answer_only_missed_failure_rate",
    "total_trials",
    "generated_at",
    "repo_url",
    "github_run_url",
    "maintainer_rerun_url",
    "evidence_sha256",
]

ALL_COLUMNS = [
    *DISPLAY_COLUMNS,
    "benchmark_name",
    "benchmark_manifest_sha256",
    "benchmark_scenario_count",
    "submission_schema_version",
    "submission_generated_by",
    "trust_level",
    "commit_sha",
    "maintainer",
    "maintainer_rerun_repository",
    "maintainer_rerun_sha",
]

FRESHNESS_LABELS = {
    "fresh": "[fresh]",
    "aging": "[aging]",
    "stale": "[stale]",
    "unknown": "[unknown age]",
}

FRESH_DAYS = 30
AGING_DAYS = 90
MIN_RECOMMENDED_TRIALS = 100
CANONICAL_BENCHMARK_NAME = "agent_anvil_trace_eval_benchmark"
CANONICAL_BENCHMARK_SCENARIO_COUNT = 5
SHA256_HEX_LENGTH = 64

COMPATIBILITY_LABELS = {
    "agent_anvil": "[agent-anvil benchmark]",
    "metadata_missing": "[metadata missing]",
    "custom": "[custom benchmark]",
    "unknown": "[unknown benchmark]",
}

HEALTH_LABELS = {
    "healthy": "[healthy]",
    "needs_review": "[needs review]",
}

SORT_COLUMNS = {
    "trace_aware_pass_rate",
    "final_answer_pass_rate",
    "answer_only_missed_failures",
    "answer_only_missed_failure_rate",
    "total_trials",
    "rank",
}


def normalize_rows(payload: dict[str, Any], *, now: datetime | None = None) -> list[dict[str, Any]]:
    raw_rows = payload.get("rows", [])
    if not isinstance(raw_rows, list):
        raw_rows = []
    now = now or datetime.now(UTC)

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
        freshness = _freshness_status(str(row.get("generated_at") or ""), now=now)
        row["freshness"] = freshness
        row["freshness_badge"] = FRESHNESS_LABELS[freshness]
        compatibility = _compatibility_status(row)
        row["compatibility"] = compatibility
        row["compatibility_badge"] = COMPATIBILITY_LABELS[compatibility]
        health_issues = _health_issues(row, freshness=freshness, compatibility=compatibility)
        row["health_issues"] = health_issues
        row["health"] = "healthy" if not health_issues else "needs_review"
        row["health_badge"] = HEALTH_LABELS[str(row["health"])]
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
    freshness: str,
    compatibility: str,
    health: str,
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
        and _matches_freshness(row, freshness)
        and _matches_compatibility(row, compatibility)
        and _matches_health(row, health)
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
    stale_rows = sum(1 for row in rows if row.get("freshness") == "stale")
    needs_review_rows = sum(1 for row in rows if row.get("health") == "needs_review")
    custom_benchmark_rows = sum(1 for row in rows if row.get("compatibility") == "custom")
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
            f"Stale rows: {stale_rows}",
            f"Needs review rows: {needs_review_rows}",
            f"Custom benchmark rows: {custom_benchmark_rows}",
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


def _matches_freshness(row: dict[str, Any], freshness: str) -> bool:
    return freshness in {"", "all"} or str(row.get("freshness") or "") == freshness


def _matches_compatibility(row: dict[str, Any], compatibility: str) -> bool:
    return compatibility in {"", "all"} or str(row.get("compatibility") or "") == compatibility


def _matches_health(row: dict[str, Any], health: str) -> bool:
    return health in {"", "all"} or str(row.get("health") or "") == health


def _freshness_status(value: str, *, now: datetime) -> str:
    generated_at = _parse_datetime(value)
    if generated_at is None:
        return "unknown"
    age_days = (now - generated_at).days
    if age_days <= FRESH_DAYS:
        return "fresh"
    if age_days <= AGING_DAYS:
        return "aging"
    return "stale"


def _compatibility_status(row: dict[str, Any]) -> str:
    benchmark_name = str(row.get("benchmark_name") or "").strip()
    if not benchmark_name:
        return "unknown"
    if benchmark_name != CANONICAL_BENCHMARK_NAME:
        return "custom"
    scenario_count = _int_or_default(row.get("benchmark_scenario_count"), 0)
    manifest_hash = str(row.get("benchmark_manifest_sha256") or "").strip()
    if (
        scenario_count < CANONICAL_BENCHMARK_SCENARIO_COUNT
        or len(manifest_hash) != SHA256_HEX_LENGTH
    ):
        return "metadata_missing"
    return "agent_anvil"


def _health_issues(row: dict[str, Any], *, freshness: str, compatibility: str) -> list[str]:
    issues: list[str] = []
    if str(row.get("trust_level") or "") == "self_reported":
        issues.append("self_reported")
    if freshness == "stale":
        issues.append("stale")
    if compatibility == "custom":
        issues.append("custom_benchmark")
    elif compatibility in {"metadata_missing", "unknown"}:
        issues.append("benchmark_metadata_missing")
    if _float_or_default(row.get("total_trials"), 0.0) < MIN_RECOMMENDED_TRIALS:
        issues.append("low_trials")
    return issues


def _parse_datetime(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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
