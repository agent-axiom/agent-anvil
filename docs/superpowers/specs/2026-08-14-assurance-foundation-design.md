# Agent Anvil Assurance Foundation Design

## Status

Approved direction, proposed repository specification.

This document defines the first independently shippable foundation for Agent
Anvil Assurance: an alpha release-contract envelope, deterministic release
identity, and an evidence trust model. It deliberately does not define a
PostgreSQL runner, environment lifecycle, state collector, fault injector,
verdict engine, or signed dossier implementation. Those are separate vertical
slices built on the contracts defined here.

## Product decision

Agent Anvil remains a stable trace-first CI evaluation harness. Assurance is a
new, additive product layer for pre-release verification of agents that change
data, code, or infrastructure.

The boundary is:

```text
Agent Anvil Core
scenario -> agent run -> trace -> assertions -> grading -> report -> CI

Agent Anvil Assurance
release contract -> reproducible environment -> independent evidence
                 -> deterministic oracles -> release verdict -> dossier
```

Trace data is evidence about the agent's declared trajectory. It is not proof
of the external state that actually changed.

## Why this approach

Three approaches were considered.

### Extend the existing scenario DSL in place

This would provide the shortest implementation path, but it would mix stable
trace assertions with stateful release semantics, force incompatible meanings
into `anvil.scenario.v1`, and make the existing core harder to understand.

### Rewrite Agent Anvil as an assurance platform

This would create cleaner names in the short term, but would discard a stable
and tested integration surface, break current users, and create a large period
where neither product is reliable.

### Add an isolated Assurance layer in the same distribution

This is the selected approach. It preserves `anvil run` and all v1 artifacts,
reuses external-agent adapters and CI conventions, and creates a clear package
boundary for the new trust model. Separate packages may be justified later for
domain packs, but not before the PostgreSQL vertical slice has external users.

## Scope

This foundation includes:

- a strict alpha `ReleaseContract` envelope;
- deterministic release-component and release-identity hashing;
- a strict `EvidenceRecord` envelope;
- evidence trust levels L0 through L3 with explicit assignment rules;
- content references and integrity hashes;
- parent and correlation links from which an evidence graph can be derived;
- evidence requirements declared by a release contract;
- JSON Schema export and golden fixtures;
- compatibility rules for future alpha revisions;
- validation APIs that can be used by later runners and pack registries.

It does not include:

- environment provisioning or teardown;
- PostgreSQL, Git, HTTP, MCP, or OTel collectors;
- state-diff execution;
- domain oracle execution;
- fault injection;
- release verdict calculation;
- exception approval workflows;
- bundle assembly, signing, or remote storage;
- a dashboard or hosted control plane;
- changes to `anvil.scenario.v1`, `anvil.trace.v1`, or current CLI behavior.

## Package boundary

New code belongs under a focused package instead of enlarging `anvil/cli.py`,
`anvil/storage.py`, or `anvil/leaderboard.py`:

```text
anvil/assurance/
  __init__.py
  contracts.py        # release contract envelope and loader
  identity.py         # canonical component and release digests
  evidence.py         # evidence records, requirements, and trust levels
  canonical.py        # canonical JSON serialization and SHA-256 helpers
  errors.py           # public validation and integrity errors
```

The existing contract registry in `anvil/contracts.py` may import and expose
the new public models. It must not become their implementation home.

Later slices may add sibling modules such as `environments/`, `collectors/`,
`oracles/`, `faults/`, `verdicts.py`, and `bundles.py`.

## Public contract versions

The first schemas use alpha identifiers:

```text
assurance.anvil.dev/release-contract/v1alpha1
assurance.anvil.dev/evidence-record/v1alpha1
```

They are not aliases for `anvil.scenario.v1`. A scenario may eventually be
referenced by a release contract, but it cannot silently become one.

Alpha compatibility rules are:

- unknown fields are rejected;
- optional fields may be added within `v1alpha1` only when old documents keep
  the same meaning;
- required-field or semantic changes use `v1alpha2`;
- a stable `v1` is created only after at least two external systems have used
  the contract and the PostgreSQL vertical slice is complete;
- generated JSON Schemas and golden fixtures are committed and tested;
- migration tools create reviewable drafts and never invent missing evidence.

## Release contract envelope

The contract identifies exactly what release is being tested, which evidence
is required, and which domain packs own extension-specific validation.

Illustrative YAML:

```yaml
apiVersion: assurance.anvil.dev/release-contract/v1alpha1
kind: ReleaseContract

metadata:
  name: refund-agent-postgres
  severity: critical
  labels:
    owner: payments-platform

release:
  components:
    - kind: agent_code
      name: refund-agent
      version: 8f5c2d1
      digest: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
    - kind: model_config
      name: openai/gpt-5-mini
      version: 2026-08-01
      digest: sha256:1123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
    - kind: prompt_bundle
      name: support-prompts
      version: v12
      digest: sha256:2123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
    - kind: tool_schema
      name: support-tools
      version: v4
      digest: sha256:3123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
    - kind: policy
      name: refund-policy
      version: v7
      digest: sha256:4123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
    - kind: environment
      name: postgres-payments
      version: v3
      digest: sha256:5123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef

actor:
  identity: refund-agent
  permissions:
    - orders.read
    - payments.refund

task:
  inputRef: fixtures/refund-order-42.json

packs:
  - name: anvil-pack-postgres
    version: ">=0.1,<0.2"

checks:
  - id: order-refunded-once
    type: postgres.row_count.v1
    config:
      table: public.refunds
      where:
        order_id: 42
      equals: 1

evidence:
  require:
    - type: postgres.state_snapshot.v1
      minimumTrust: L2
      subject: postgres://payments/public
    - type: agent.trace.v1
      minimumTrust: L1

reliability:
  trials: 20
  minimumPassRate: 0.95
```

### Contract invariants

- `apiVersion` and `kind` are exact discriminators.
- Metadata names are non-empty and stable within a contract collection.
- A runnable alpha contract has exactly one component of each mandatory kind:
  `agent_code`, `model_config`, `prompt_bundle`, `tool_schema`, `policy`, and
  `environment`.
- Component digests use `sha256:<64 lowercase hex characters>`.
- Duplicate `(kind, name)` components are invalid.
- Task input is inline or referenced, never both.
- Check IDs are unique.
- Check types are namespaced and versioned.
- Every check type belongs to a declared compatible pack.
- Evidence requirements use namespaced, versioned types.
- Trials are positive and minimum pass rate is between zero and one.
- The contract envelope does not evaluate arbitrary Python, SQL, JMESPath, or
  expression-language code.

The default state policy for future state scopes is closed-world: effects not
explicitly allowed by the contract are not implicitly allowed. Domain packs
must make any broader scope explicit.

## Extension and pack validation

The core validates the common check envelope:

```text
id
type
config
```

The pack named by the contract validates `config` for its own check types. A
loader receives a `CheckTypeRegistry` dependency; it does not import arbitrary
Python packages named by untrusted YAML.

Unknown packs, incompatible pack versions, unknown check types, or invalid
pack-specific configuration are controlled validation failures. Dynamic pack
discovery and publisher trust are deferred to the Pack SDK design.

Pack versions use Python package version and specifier semantics. The registry,
not the contract document, resolves the installed pack version.

Tests use an in-memory fake registry so the foundation does not depend on a
PostgreSQL implementation.

## Release identity

A release is the tested combination, not only a Git commit.

The alpha component kinds are:

```text
agent_code
model_config
prompt_bundle
tool_schema
policy
environment
adapter
memory_schema
```

Each component contains `kind`, `name`, `version`, `digest`, and optional
non-secret metadata. The release identity is the SHA-256 digest of canonical
JSON containing the sorted component list.

Canonicalization rules are:

- UTF-8 JSON;
- object keys sorted lexicographically;
- no insignificant whitespace;
- arrays preserve order unless the owning model explicitly defines them as a
  set before serialization;
- release components are sorted by `(kind, name, version, digest)`;
- timestamps and machine-specific paths are excluded;
- secrets and raw prompts are never included, only approved metadata and
  content digests.

The release identity changes whenever any included component changes. A
runnable alpha contract missing a mandatory component is invalid and cannot be
executed. A future migration helper may emit a separate, explicitly non-runnable
draft artifact, but it may not weaken `ReleaseContract` validation.

## Evidence trust model

Trust levels describe how evidence was observed, not whether its content is
favorable to the agent.

### L0: self-reported

The agent or a tool result controlled by the agent reports the event. Examples
include final text, agent-emitted JSONL, and claimed tool outcomes.

### L1: instrumented

An SDK, adapter, or in-process hook records the event, but it shares the
agent's execution or write boundary. Current Agent Anvil traces normally fall
into L0 or L1 depending on their source.

### L2: independently observed

A collector outside the agent's write boundary observes the state or event
using separate credentials. Examples include a read-only PostgreSQL collector,
a gateway log, or a host-side filesystem probe.

### L3: attested

L2 evidence is bound to an authenticated collector and protected runner, and
its manifest is signed or covered by a verifiable provenance attestation.

Trust levels are assigned by trusted Anvil configuration and collector
registration. Parsing an evidence record only validates its shape; verification
must compare the claimed level and source against a separately supplied trust
policy. An evidence-producing process cannot raise its own level by writing
`trustLevel: L3` into output.

L2 does not mean tamper-proof. L3 does not prove that the host, trust root, or
collector implementation is uncompromised. Claims must state the tested
boundary and remaining assumptions.

## Evidence record

An evidence record is a compact, inspectable envelope around content stored in
the run's content-addressed artifact store.

Illustrative JSON:

```json
{
  "schemaVersion": "assurance.anvil.dev/evidence-record/v1alpha1",
  "evidenceId": "sha256:6123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "runId": "assure_20260814_001",
  "releaseId": "sha256:7123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "contractId": "refund-agent-postgres",
  "type": "postgres.state_snapshot.v1",
  "trustLevel": "L2",
  "subject": "postgres://payments/public",
  "source": {
    "collector": "anvil-postgres-collector",
    "version": "0.1.0",
    "boundary": "separate-read-only-credentials"
  },
  "observedAt": "2026-08-14T12:00:00Z",
  "content": {
    "mediaType": "application/json",
    "sha256": "8123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "sizeBytes": 4096,
    "path": "objects/81/23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  },
  "parents": [],
  "correlations": {
    "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
    "transactionId": "735128"
  },
  "redaction": {
    "applied": true,
    "policyDigest": "sha256:9123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  }
}
```

### Evidence invariants

- Evidence IDs use `sha256:<64 lowercase hex characters>`. Content hashes use
  64 lowercase hexadecimal characters in the `content.sha256` field.
- `evidenceId` is the SHA-256 digest of canonical record metadata excluding the
  `evidenceId` field itself. It includes `observedAt`, so two independently
  observed events can remain distinct even when they reference identical bytes.
- `releaseId` equals the canonical release identity for the run.
- Evidence type names are namespaced and versioned.
- The source includes collector identity, version, and boundary description.
- L2 and L3 records require a non-empty independent boundary declaration.
- Content paths are relative, normalized, and cannot escape the run store.
- Content size and digest must match the referenced bytes when verified.
- Parent IDs cannot contain duplicates or refer to the record itself.
- A validated graph cannot contain cycles.
- Correlation values are identifiers, not evidence of causality by themselves.
- Raw secrets are forbidden in metadata and correlation fields.
- `observedAt` does not affect `content.sha256`; that digest identifies only the
  referenced bytes.

The evidence graph is derived from record IDs, parent links, and correlation
metadata. The foundation does not introduce a graph database.

## Evidence requirements

A release contract declares the minimum evidence required for a claim. A
requirement contains:

```text
type
minimumTrust
subject
minimumCount (default 1)
```

Later runners may add selectors such as trial or phase. The alpha foundation
does not add a generic boolean expression language.

Trust comparison is monotonic: L3 satisfies an L2 requirement, but L1 does not.
Type and subject must also match. Missing, malformed, digest-mismatched, or
below-threshold evidence cannot satisfy a requirement.

The future verdict policy is fixed now:

- a deterministic contract violation produces `BLOCK`;
- missing or unverifiable required evidence produces `INCONCLUSIVE`;
- neither condition may be converted to `PASS` by an LLM grader;
- `PASS_WITH_EXCEPTION` requires a separately authenticated, scoped, expiring
  exception record and is outside this foundation.

## Data flow

The foundation's validation flow is:

```text
release-contract YAML
  -> strict envelope parsing
  -> pack/check registry validation
  -> canonical release identity
  -> evidence requirement model

evidence-record JSON
  -> strict envelope parsing
  -> trust assignment check
  -> content path/digest verification
  -> release identity binding
  -> parent/correlation graph validation
```

Future execution builds on these boundaries:

```text
contract
  -> environment provider
  -> agent runner
  -> independent collectors
  -> evidence records and content objects
  -> domain oracles
  -> verdict
  -> signed dossier
```

## Error model

Public validation failures derive from one Assurance-specific base error and
carry a stable machine-readable code plus a human-readable field path.

Initial error categories are:

```text
contract_parse_error
contract_schema_error
unknown_pack
incompatible_pack
unknown_check_type
check_config_error
release_identity_incomplete
evidence_schema_error
evidence_trust_error
evidence_content_missing
evidence_digest_mismatch
evidence_path_escape
evidence_graph_cycle
```

Expected validation failures do not print Python tracebacks in CLI surfaces.
Errors never include raw secret values or unbounded external-process output.

## Security and privacy boundaries

The foundation assumes the Anvil process and configured trust policy are part
of the trusted computing base. It is designed to detect malformed or tampered
artifacts and to distinguish agent-reported evidence from independently
observed evidence.

It does not defend against:

- host root compromise;
- a compromised collector implementation;
- a dishonest trust-policy administrator;
- a compromised signing root;
- a model provider lying about model identity;
- an environment image whose declared digest does not represent its runtime;
- side effects outside all configured collectors.

Evidence content remains local by default. Collectors must apply redaction
before persistence when the content may contain secrets or personal data.
Metadata is minimized, and release identity uses hashes rather than raw prompts,
tool definitions, policies, or credentials.

## Compatibility with current Agent Anvil

- Existing scenario, trace, results, manifest, leaderboard, and attestation
  schemas remain unchanged.
- `anvil run`, `anvil report`, and current exit codes remain unchanged.
- Current external JSONL and HTTP agent adapters can be reused by a future
  Assurance runner.
- Current traces may be referenced as L0/L1 evidence but are never silently
  promoted to L2.
- Existing run manifests are not release dossiers.
- Existing GitHub artifact-attestation support may later attest a dossier, but
  leaderboard attestation reports are not reused as Assurance evidence.
- A future v1-to-Assurance migration command can generate a draft contract,
  but it must mark unavailable release components and state evidence as missing.

## Testing strategy

The implementation plan must use TDD and include:

- strict model tests for every required field and discriminator;
- unknown-field rejection tests;
- duplicate component and check-ID tests;
- canonicalization golden vectors;
- release digest stability across mapping order and machine paths;
- release digest changes for every component field that affects behavior;
- pack-registry success, unknown-type, and incompatible-version tests;
- evidence trust assignment and monotonic comparison tests;
- path traversal and symlink escape tests for content references;
- missing content, wrong size, and digest mismatch tests;
- parent self-reference, duplicate-parent, missing-parent, and cycle tests;
- schema export and golden-fixture tests;
- legacy v1 regression tests;
- property-based tests for canonicalization and graph invariants if adding
  Hypothesis does not leak into runtime dependencies.

The full project gate remains:

```bash
uv run ruff format --check
uv run ruff check
uv run ty check
uv run pytest -q
```

Coverage must remain at or above the repository's 90 percent threshold.

## Acceptance criteria

This foundation is complete when:

1. Valid contract and evidence fixtures round-trip through Pydantic models and
   exported JSON Schemas.
2. A release identity is reproducible across machines and changes whenever a
   behavior-affecting component changes.
3. The core rejects unknown packs and check types without dynamic imports from
   contract data.
4. L0/L1 evidence cannot satisfy an L2 requirement.
5. Referenced evidence with missing bytes, path escape, or a wrong digest is
   rejected deterministically.
6. Cyclic or dangling evidence-parent relationships are rejected.
7. Current v1 artifacts and commands retain their existing behavior.
8. Documentation states exactly what each trust level proves and does not
   describe any level as proof that an agent is generally safe.
9. No PostgreSQL-specific runtime dependency is added to the base install.
10. The next PostgreSQL vertical-slice spec can depend on these interfaces
    without changing their common envelope semantics.

## Follow-on specifications

Implementation proceeds through separate, reviewable designs in this order:

1. PostgreSQL environment lifecycle and trust boundary.
2. PostgreSQL pre/post snapshot collector and typed state oracles.
3. Integrated Assurance runner and verdict engine.
4. Deterministic fault injection for timeout-after-commit, duplicate delivery,
   and stale reads.
5. Release dossier assembly, verification, and provenance attestation.
6. GitHub Action gate and `trace passes, state fails` public benchmark.
7. OTel import/export and observability-platform bridges.

Git, dbt, Airflow, Kafka, Kubernetes, enterprise control-plane features, and a
pack registry remain demand-gated after the PostgreSQL slice and external pilot.

## Product validation gate

Technical work proceeds in parallel with customer discovery. The PostgreSQL
vertical slice should not be broadened unless interviews produce:

- one concrete agent currently blocked from production or permission growth;
- one real release checklist and accountable `go/no-go` owner;
- one incident or near miss that trace-only evaluation did not resolve;
- access to an anonymized fixture or representative test environment;
- willingness to use the verdict in a release decision.

If qualified teams consistently report that pytest plus their observability and
eval stack is sufficient, Agent Anvil should not expand into a generic control
plane. The narrower fallback is a domain-pack SDK and assurance methodology for
existing platforms.
