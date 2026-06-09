from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any


def test_space_normalizes_maintainer_rerun_evidence_aliases() -> None:
    view: Any = _load_space_view_module()

    rows = view.normalize_rows(
        {
            "rows": [
                {
                    "rank": 1,
                    "agent_name": "Support Agent",
                    "trust_level": "maintainer_rerun",
                    "generated_at": "2026-06-09T00:00:00Z",
                    "total_trials": 100,
                    "benchmark_name": "agent_anvil_trace_eval_benchmark",
                    "benchmark_manifest_sha256": "a" * 64,
                    "benchmark_scenario_count": 5,
                    "maintainer_rerun_url": "https://github.com/owner/repo/actions/runs/123",
                    "maintainer_rerun_github_repository": "owner/repo",
                    "maintainer_rerun_github_sha": "abc123",
                }
            ]
        },
        now=datetime(2026, 6, 10, tzinfo=UTC),
    )

    assert rows[0]["maintainer_rerun_repository"] == "owner/repo"
    assert rows[0]["maintainer_rerun_sha"] == "abc123"
    assert rows[0]["trust_badge"] == "[maintainer rerun]"


def _load_space_view_module() -> ModuleType:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "integrations"
        / "huggingface"
        / "leaderboard_space"
        / "leaderboard_view.py"
    )
    spec = importlib.util.spec_from_file_location("leaderboard_view_under_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
