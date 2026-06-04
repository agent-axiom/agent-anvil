# Stable Contracts V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish stable JSON Schema contracts and golden fixtures for Agent
Anvil traces, scenarios, leaderboard submissions, and leaderboard indexes.

**Architecture:** Add a small schema contract module that exports JSON Schema
from the existing Pydantic source-of-truth models. Keep runtime behavior
unchanged and guard the public contracts with tests and checked-in fixtures.

**Tech Stack:** Pydantic JSON Schema, Typer CLI, pytest, Markdown docs.

---

### Task 1: RED Contract Tests

**Files:**
- Create: `tests/test_contracts.py`

- [x] Add tests for `anvil schema export --out`.
- [x] Add tests that checked-in `schemas/*.schema.json` match exported schemas.
- [x] Add tests that golden fixtures load through Pydantic models.
- [x] Add tests that README/artifacts/schema-versioning docs link contracts.

### Task 2: Schema Export Implementation

**Files:**
- Create: `anvil/contracts.py`
- Modify: `anvil/cli.py`

- [x] Add contract metadata for trace, scenario, leaderboard submission, and
      leaderboard index.
- [x] Export draft 2020-12 JSON Schema with stable `$id` and
      `x-agent-anvil-schema-version`.
- [x] Add `anvil schema export --out schemas`.

### Task 3: Checked-In Schemas And Fixtures

**Files:**
- Create: `schemas/*.schema.json`
- Create: `fixtures/contracts/*`

- [x] Generate checked-in schemas from the CLI.
- [x] Add valid trace, failed protocol trace, scenario, leaderboard submission,
      and leaderboard index fixtures.

### Task 4: Contracts Documentation

**Files:**
- Create: `docs/contracts.md`
- Modify: `README.md`
- Modify: `docs/artifacts.md`
- Modify: `docs/schema-versioning.md`

- [x] Document schema export, fixture usage, and External JSONL conformance.
- [x] Link contracts from README and artifact index.

### Task 5: Verify And Ship

**Files:**
- No additional files expected.

- [x] Run RED tests first and confirm expected missing-command/file failures.
- [x] Run targeted contract tests after implementation.
- [x] Run full pytest coverage gate, ruff format/check, and ty.
- [ ] Commit, push, open PR, wait for CI, and merge when green.
