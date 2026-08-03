# Leaderboard Artifact Attestation Verification Design

## Goal

Add cryptographic provenance verification for public leaderboard submission
files. Maintainers must be able to prove that a submitted JSON artifact was
produced by the repository and source revision claimed inside the submission,
then consume that proof without repeating network calls during audit.

## Trust Model

Agent Anvil delegates signature, certificate, transparency-log, and SLSA
predicate verification to GitHub CLI's `gh attestation verify`. Agent Anvil
adds leaderboard-specific policy:

- the repository is taken from the validated `github_actions` submission;
- the source digest defaults to the submission's claimed GitHub SHA;
- self-hosted runners are denied by default;
- an optional signer workflow and source ref can narrow signer identity;
- the verified statement must include the local submission file's SHA-256;
- only a compact, versioned verification report is persisted.

The report records the policy passed to `gh`, the verified subject digest, the
number of verified attestations, and a digest of the JSON verification output.
It intentionally does not persist certificate bundles or user-controlled SLSA
predicate data.

## Public Interface

The single-file command is:

```bash
anvil leaderboard verify-attestation leaderboard_submission.json \
  --out artifact_attestation_verification.json
```

Optional policy controls are `--signer-workflow`, `--source-ref`, `--bundle`,
`--timeout-seconds`, and
`--deny-self-hosted-runners/--allow-self-hosted-runners`. `--json` prints the
stable report to stdout.

The persisted contract is
`agent-anvil.leaderboard.artifact_attestation_verification.v1`.

Batch GitHub-run verification gains `--artifact-attestations`. When enabled,
it writes one artifact-attestation report beside each GitHub-run report and
links it from the existing evidence index. Audit gains
`--require-artifact-attestation`; it consumes the linked report locally and
rejects missing, malformed, or mismatched evidence.

## Components

`anvil/attestations.py` owns GitHub CLI execution, output parsing, digest
binding, and the stable report model. It imports leaderboard validation lazily
so the leaderboard module can validate attestation reports without a circular
module dependency.

`anvil/leaderboard.py` links verified reports into the existing evidence index
and projects their status into audit rows. It does not invoke GitHub CLI during
audit.

`anvil/contracts.py` exports the report JSON Schema. Golden fixtures and schema
tests protect compatibility.

## Failure Behavior

Missing files, invalid trust metadata, missing or timed-out GitHub CLI,
non-zero verification, malformed JSON, empty results, and subject-digest
mismatches become controlled `LeaderboardValidationError` failures. Error text
is bounded and excludes raw attestation bundles.

Batch verification fails closed when artifact verification is requested. Audit
also fails closed when `--require-artifact-attestation` is set and evidence is
missing or inconsistent. Existing workflows remain backward compatible unless
they opt into the new requirement.

## Testing

Tests replace GitHub CLI execution with deterministic completed-process
fixtures. Coverage includes command construction, successful digest binding,
missing CLI, timeout, non-zero exit, malformed output, subject mismatch,
contract export, batch evidence-index linkage, and audit rejection on missing
or tampered attestation evidence.
