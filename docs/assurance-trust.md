# Assurance Evidence Trust

Agent Anvil Assurance separates evidence shape from evidence trust. A producer
may write a structurally valid record, but verifier-controlled configuration
decides whether the claimed source and trust level are acceptable.

**Trust describes observation provenance, not whether the agent is safe.**

## Levels

### L0: Self-Reported

The agent, or a tool result under the same control boundary, reports what
happened. Examples include final text, agent-emitted JSONL, and claimed tool
outcomes. L0 is useful for debugging but is not independent evidence of side
effects.

### L1: Instrumented

An SDK, adapter, or in-process hook records the event. The instrumentation
shares the agent's process or write boundary, so a compromised or incorrect
agent boundary may influence both behavior and record. Existing Agent Anvil
traces are normally L0 or L1 depending on their source.

### L2: Independently Observed

A collector outside the agent's write boundary observes state or events with
separate credentials. A read-only database collector, gateway log, or host-side
probe can provide L2 evidence. L2 requires a non-empty boundary declaration.

L2 is not tamper-proof. It states that the configured observer was independent
of the tested agent boundary under the documented assumptions.

### L3: Attested

L3 starts with L2 observation and binds it to an authenticated collector and a
protected runner through a signed manifest or verifiable provenance
attestation. Signing and dossier assembly are not implemented in this
foundation, so current code only models and verifies an externally configured
L3 assignment.

L3 does not prove that the host root, collector implementation, trust root,
model provider, or environment integrity is uncompromised.

## Assignment Rules

The evidence record carries `source` and `trustLevel` claims. A separate
`EvidenceTrustPolicy` assigns a maximum level to an exact collector, version,
and boundary tuple. Verification rejects unknown sources and claims above the
configured maximum. A lower claim is never silently promoted.

For example, writing `trustLevel: L3` into agent output does not establish L3.
The record remains unverified until trusted configuration contains a matching
L3 assignment. The producer cannot self-elevate through the evidence payload.

Trust comparison for requirements is monotonic only after verification: L3
can satisfy an L2 requirement, while L1 cannot. Evidence type, optional subject,
and minimum count must also match.

## Integrity Checks

The foundation verifies:

- canonical `evidenceId` metadata hashing;
- exact release identity binding;
- verifier-controlled source trust assignment;
- normalized relative content paths and store containment;
- missing content, byte size, and SHA-256;
- duplicate, self, dangling, and cyclic parent relationships;
- monotonic evidence requirements over `VerifiedEvidence` only.

`content.sha256` identifies referenced bytes. `evidenceId` identifies the full
record metadata except the ID itself and includes `observedAt`, so two separate
observations of identical bytes remain distinct.

## Security Boundary

The Anvil process and trust-policy administrator are in the trusted computing
base. This foundation does not defend against:

- host root compromise;
- a compromised collector implementation;
- a dishonest trust-policy administrator;
- a compromised signing or trust root;
- a model provider lying about model identity;
- an environment whose declared digest does not represent its runtime;
- side effects outside all configured collectors.

Evidence content is local by default. Collectors must redact secrets and
personal data before persistence. Release identity contains component digests
and stable identifiers, not raw prompts, policies, tool definitions, machine
paths, or credentials.

## Current Scope

This alpha provides contracts and deterministic verification primitives. There
is no Assurance runner, no environment lifecycle, no independent collector,
no domain oracle, no verdict engine, no exception workflow, no dossier signing,
and no hosted control plane in this foundation.

The next planned vertical slice is a disposable PostgreSQL environment with
separate read-only observation credentials. It will consume these contracts
without changing their common envelope semantics.
