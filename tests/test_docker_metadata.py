from __future__ import annotations

from pathlib import Path

import yaml


def test_dockerfile_default_runs_passing_smoke_eval() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert dockerfile.startswith("FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim")
    assert 'CMD ["anvil", "run", "scenarios/external_jsonl_agent.yaml", "--offline"]' in dockerfile


def test_compose_exposes_smoke_regression_and_openai_services() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))

    services = compose["services"]
    assert services["anvil-smoke"]["command"] == [
        "anvil",
        "run",
        "scenarios/external_jsonl_agent.yaml",
        "--offline",
    ]
    assert services["anvil-regression-demo"]["command"] == [
        "anvil",
        "run",
        "scenarios/refund_agent.yaml",
        "--offline",
        "--agent-mode",
        "offline",
        "--trials",
        "1",
    ]
    assert services["anvil-openai"]["command"] == [
        "anvil",
        "run",
        "scenarios/refund_agent.yaml",
        "--agent-mode",
        "openai",
    ]
