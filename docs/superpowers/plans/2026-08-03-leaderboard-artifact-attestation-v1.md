# Leaderboard Artifact Attestation Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify GitHub artifact attestations for leaderboard submissions and make the resulting proof enforceable by the existing evidence-index audit path.

**Architecture:** A focused `anvil.attestations` module wraps `gh attestation verify`, applies submission-derived policy, and emits a stable compact report. The leaderboard evidence index links that report, while audit validates the link and digest entirely from local artifacts.

**Tech Stack:** Python 3.12+, Pydantic v2, Typer, GitHub CLI, pytest, checked-in JSON Schema contracts.

---

### Task 1: Single-artifact verification contract

**Files:**
- Create: `anvil/attestations.py`
- Modify: `anvil/contracts.py`
- Modify: `anvil/cli.py`
- Test: `tests/test_attestations.py`
- Test: `tests/test_contracts.py`

- [ ] Write failing tests for successful verification, repository/source policy command arguments, subject SHA-256 binding, JSON output, and report persistence.
- [ ] Run `uv run pytest tests/test_attestations.py -q` and confirm failures are caused by the missing module and command.
- [ ] Implement `LeaderboardArtifactAttestationVerification` and `verify_leaderboard_artifact_attestation` with a replaceable command runner.
- [ ] Add `leaderboard verify-attestation` with controlled text/JSON output and policy options.
- [ ] Run the focused tests and confirm they pass.

### Task 2: Fail-closed external process handling

**Files:**
- Modify: `anvil/attestations.py`
- Modify: `tests/test_attestations.py`

- [ ] Write failing tests for missing `gh`, timeout, non-zero exit, malformed JSON, empty verification results, and subject-digest mismatch.
- [ ] Run the focused tests and confirm each new test fails for the intended reason.
- [ ] Implement bounded controlled errors without persisting raw bundles or unbounded stderr.
- [ ] Run the focused tests and confirm they pass.

### Task 3: Stable schema and golden fixture

**Files:**
- Create: `fixtures/contracts/leaderboard-artifact-attestation-verification-valid.json`
- Create: `schemas/agent-anvil.leaderboard.artifact_attestation_verification.v1.schema.json`
- Modify: `anvil/contracts.py`
- Modify: `tests/test_contracts.py`
- Modify: `docs/contracts.md`
- Modify: `docs/schema-versioning.md`
- Modify: `docs/artifacts.md`

- [ ] Write failing contract registry and golden-fixture tests.
- [ ] Register the Pydantic model and export the schema with `uv run anvil schema export --out schemas`.
- [ ] Add the valid fixture and document the public contract.
- [ ] Run `uv run pytest tests/test_contracts.py -q` and confirm it passes.

### Task 4: Evidence index and audit enforcement

**Files:**
- Modify: `anvil/leaderboard.py`
- Modify: `anvil/cli.py`
- Modify: `tests/test_leaderboard.py`
- Modify: `schemas/agent-anvil.leaderboard.evidence_index.v1.schema.json`
- Modify: `schemas/agent-anvil.leaderboard.audit.v1.schema.json`

- [ ] Write failing tests showing batch verification links an attestation report and audit accepts it without running GitHub CLI.
- [ ] Write failing tests showing `--require-artifact-attestation` rejects missing, malformed, or digest-mismatched reports.
- [ ] Add optional attestation fields to evidence refs and audit rows, preserving old v1 documents through defaults.
- [ ] Add `verify-all --artifact-attestations` and `audit --require-artifact-attestation`.
- [ ] Re-export schemas and run focused leaderboard tests.

### Task 5: Maintainer workflow and user documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/cli.md`
- Modify: `docs/leaderboard.md`
- Modify: `docs/release-provenance.md`
- Modify: `docs/examples/leaderboard-index-workflow.yml`
- Modify: `tests/test_community_docs.py`

- [ ] Update the copy-paste workflow to generate attestation evidence before enforcing it in audit.
- [ ] Explain online and bundle-based verification, signer narrowing, self-hosted policy, and the distinction between GitHub-run and artifact provenance.
- [ ] Add documentation assertions for the new command and workflow flags.
- [ ] Run focused documentation tests.

### Task 6: Verify, publish, and integrate

**Files:**
- Modify only files required by formatter or version synchronization.

- [ ] Run `uv run ruff format --check`.
- [ ] Run `uv run ruff check`.
- [ ] Run `uv run ty check`.
- [ ] Run `PATH=/Users/if/.nvm/versions/node/v24.14.1/bin:$PATH uv run pytest -q`.
- [ ] Commit granularly, push, open a pull request, wait for Python 3.12/3.14 and demo CI, then merge.
- [ ] Release the next core version, update the Marketplace Action core ref, release the wrapper, move `v1`, and synchronize pinned wrapper references in the core repository.

