# Paper Benchmark Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reproducible benchmark pack that makes Agent Anvil usable as the empirical artifact for an arXiv systems preprint.

**Architecture:** Add a small `anvil.benchmark` module for manifests, baseline scoring, aggregation, and Markdown rendering. Wire it into Typer as `anvil bench`, then add paper-facing `experiments/` and `docs/paper/` artifacts.

**Tech Stack:** Python 3.12+, Typer, Pydantic, existing Agent Anvil runner/storage/report models, pytest, ruff, ty.

---

### Task 1: Benchmark Data Model

**Files:**
- Create: `anvil/benchmark.py`
- Create: `tests/test_benchmark.py`

- [ ] Add Pydantic models for a benchmark manifest with fields `name`, `description`, `suites`, and `output`.
- [ ] Add a loader for YAML manifests.
- [ ] Add tests that reject unknown fields and empty suite lists.
- [ ] Commit as `Add benchmark manifest model`.

### Task 2: Final-Answer Baseline

**Files:**
- Modify: `anvil/benchmark.py`
- Modify: `tests/test_benchmark.py`

- [ ] Add `class FinalAnswerBaseline`.
- [ ] Mark a trace as passing when `final_output` exists and does not contain obvious runtime failure terms.
- [ ] Add tests showing a clean final answer passes even when a forbidden tool appears in the trace.
- [ ] Commit as `Add final-answer benchmark baseline`.

### Task 3: Benchmark Runner

**Files:**
- Modify: `anvil/benchmark.py`
- Modify: `anvil/cli.py`
- Modify: `tests/test_benchmark.py`
- Modify: `tests/test_cli.py`

- [ ] Add `run_benchmark(manifest_path, offline, runs_dir, out_json, out_md)`.
- [ ] Internally call existing `run_suite` for each manifest suite.
- [ ] Aggregate answer-only and trace-aware pass rates.
- [ ] Add `anvil bench` CLI with `--offline`, `--runs-dir`, `--out`, and `--markdown-out`.
- [ ] Commit as `Add benchmark runner CLI`.

### Task 4: Paper Experiment Pack

**Files:**
- Create: `experiments/paper.yaml`
- Create: `experiments/scenarios/*.yaml`
- Create or reuse: `examples/*_agent.py`
- Modify: `tests/test_benchmark.py`

- [ ] Add 3-5 small scenario suites covering refund, tool safety, account admin, operations, and external-agent protocol behavior.
- [ ] Ensure at least one scenario passes final-answer baseline and fails trace-aware checks.
- [ ] Add a smoke test that the paper manifest loads and references existing files.
- [ ] Commit as `Add paper benchmark scenarios`.

### Task 5: Paper Artifacts

**Files:**
- Create: `docs/paper/artifact.md`
- Create: `docs/paper/results.md`
- Create: `docs/paper/limitations.md`
- Modify: `README.md`

- [ ] Run the benchmark offline and save stable JSON/Markdown result artifacts.
- [ ] Document exact reproduction commands.
- [ ] Add a short README link to the paper artifact docs without making README heavier.
- [ ] Commit as `Add paper benchmark artifacts`.

### Task 6: Verification and PR

**Files:**
- Modify as needed from failures only.

- [ ] Run `uv run --frozen ruff format --check .`.
- [ ] Run `uv run --frozen ruff check .`.
- [ ] Run `uv run --frozen ty check`.
- [ ] Run `uv run --frozen pytest`.
- [ ] Push `codex/paper-benchmark-pack`.
- [ ] Open a PR against `main` with a concise description and reproduction commands.
