# Agent Anvil MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python-first CI evaluation harness that runs YAML scenario suites, records tool-agent traces, grades behavior, clusters failures, and writes JSON/Markdown reports.

**Architecture:** The CLI loads a YAML suite into Pydantic models, invokes a pluggable example or external agent for each scenario trial, records trace JSON, runs deterministic checks plus an OpenAI semantic grader, aggregates failures, and persists run artifacts under `runs/<run_id>/`. The demo agent is deterministic by default so tests and local demos do not require credentials, while OpenAI mode uses the official SDK for tool calling and semantic grading when `OPENAI_API_KEY` is available.

**Tech Stack:** Python 3.14 runtime target with `requires-python >=3.12`, `uv` for environment and locking, Typer for CLI, Pydantic for schemas, PyYAML for scenario loading, OpenAI Python SDK Responses API for semantic grading, Ruff for lint/format, ty for type checking, pytest with fixtures, parametrization, coverage, mock, asyncio, randomly, and sugar plugins.

---

### File Structure

- `pyproject.toml`: package metadata, dependencies, CLI entrypoint, pytest, Ruff, and ty config.
- `README.md`: product positioning, quickstart, commands, OpenAI usage, CI notes.
- `.env.example`: documented environment variables for OpenAI-enabled runs.
- `Dockerfile` and `docker-compose.yml`: reproducible CLI execution.
- `anvil/scenario.py`: YAML loading and scenario Pydantic models.
- `anvil/trace.py`: trace step/run schemas and metric helpers.
- `anvil/grading.py`: deterministic checks, semantic grade schema, OpenAI grader, offline heuristic grader.
- `anvil/clustering.py`: failure grouping and repair-plan aggregation.
- `anvil/report.py`: Markdown and JSON result rendering.
- `anvil/storage.py`: run directory, trace, result, report, and `runs/latest` handling.
- `anvil/runner.py`: suite orchestration.
- `anvil/cli.py`: `anvil run`, `anvil report`, `anvil repair`, and `anvil compare`.
- `examples/support_agent/`: offline and OpenAI tool-calling refund agents, tools, and prompt.
- `scenarios/`: refund and Kubernetes debug demo suites.
- `tests/`: behavior-first tests for loaders, trace schemas, grading, reports, runner, and CLI.

### Tasks

- [ ] Create project metadata and tool configuration.
- [ ] Write failing tests for scenario loading and validation.
- [ ] Implement scenario models and YAML loader.
- [ ] Write failing tests for trace schema round trips and metrics.
- [ ] Implement trace schemas.
- [ ] Write failing tests for deterministic grading.
- [ ] Implement deterministic and semantic grading abstractions.
- [ ] Write failing tests for clustering and report generation.
- [ ] Implement clustering and Markdown/JSON report rendering.
- [ ] Write failing tests for runner storage artifacts and CLI commands.
- [ ] Implement storage, runner, CLI, demo agent, and demo scenarios.
- [ ] Add README, `.env.example`, Dockerfile, and compose file.
- [ ] Run `uv lock`, `uv run ruff format`, `uv run ruff check`, `uv run ty check`, and `uv run pytest`.

### Self-Review

- Spec coverage: every MVP requirement maps to a module and test area above.
- Placeholder scan: no implementation placeholders are left in this plan.
- Type consistency: scenario, trace, grade, cluster, and report names match the intended module boundaries.
