# Release Provenance

Agent Anvil releases should be easy to inspect and reproduce from the public
repository state.

## Release Checklist

Before publishing a release:

1. Update `pyproject.toml`.
2. Run `uv lock` so `uv.lock` matches the package version.
3. Update docs that pin `git+https://github.com/agent-axiom/agent-anvil@vX.Y.Z`.
4. Run the local quality gate:

   ```bash
   uv run pytest --cov=anvil --cov-report=term-missing --cov-report=xml --cov-fail-under=90
   uv run ruff format --check
   uv run ruff check
   uv run ty check
   ```

5. Merge through a pull request with GitHub Actions green.
6. Publish a GitHub release from the merged commit.
7. Confirm the release page is public and marked latest when intended.

## GitHub Actions

Every main-branch release candidate should have:

- `CI` passing on supported Python versions;
- `Agent Anvil` passing against the project itself;
- coverage meeting the configured threshold;
- uploaded artifacts for CI runs where applicable.

The project uses GitHub Actions as public release evidence, but release tags are
the source of truth for installable refs.

## Artifact Attestation

The public leaderboard workflow can create a GitHub artifact attestation for
`leaderboard_submission.json`. That artifact attestation proves the aggregate
submission file was produced by the claimed GitHub Actions run.

Artifact attestations complement, but do not replace:

- Agent Anvil submission validation;
- benchmark and scenario hashes;
- maintainer review;
- optional maintainer reruns.

## What Is Not Proven

Release provenance does not prove that an arbitrary submitted agent is honest,
that a benchmark cannot be gamed, or that all tool side effects were safe. It
provides inspectable evidence: source ref, CI result, generated artifacts, and
hashes that reviewers can compare.

## Current Distribution Model

Agent Anvil is distributed from GitHub source refs and releases. The GitHub
Action wrapper is published separately as
`agent-axiom/agent-anvil-action@v1.0.6`.

If binary wheels or signed artifacts are added later, this document should be
updated with checksum and signature verification steps.
