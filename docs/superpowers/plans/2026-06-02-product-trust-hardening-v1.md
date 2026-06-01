# Product Trust Hardening V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first Trust Center layer that makes Agent Anvil's security,
privacy, stability, schema, and release-provenance contracts explicit.

**Architecture:** This is documentation-first hardening, guarded by doc tests.
The runtime remains unchanged; the value is product trust, clearer public
boundaries, and stable links from README/artifacts/contributor docs.

**Tech Stack:** Markdown docs, pytest doc regression tests, existing CI.

---

### Task 1: Guard Trust Docs With Tests

**Files:**
- Modify: `tests/test_community_docs.py`

- [x] Add a failing test that requires `SECURITY.md`, Trust Center docs, privacy,
      stability, schema-versioning, release-provenance, and public links.
- [x] Run the test and verify it fails because `SECURITY.md` does not exist.

### Task 2: Add Trust Documentation

**Files:**
- Create: `SECURITY.md`
- Create: `docs/trust.md`
- Create: `docs/privacy.md`
- Create: `docs/stability.md`
- Create: `docs/schema-versioning.md`
- Create: `docs/release-provenance.md`

- [x] Write concise, product-facing docs that separate stable core from
      experimental helpers.
- [x] Avoid claims that Agent Anvil sandboxes arbitrary code or prevents all
      benchmark gaming.

### Task 3: Link Trust Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/artifacts.md`
- Modify: `CONTRIBUTING.md`

- [x] Link trust docs from the README Start Here list and More section.
- [x] Link trust docs from the artifact index.
- [x] Link `SECURITY.md` from contributor privacy/security guidance.

### Task 4: Verify And Ship

**Files:**
- No additional files expected.

- [x] Run targeted doc tests.
- [x] Run full pytest coverage gate, ruff format/check, and ty.
- [ ] Commit, push, open PR, wait for CI, and merge when green.
