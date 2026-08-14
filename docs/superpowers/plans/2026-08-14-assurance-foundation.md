# Assurance Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add strict, versioned release and evidence contracts that give future Agent Anvil Assurance runners a reproducible release identity and a non-self-asserted evidence trust boundary.

**Architecture:** Keep the existing scenario runner and artifact contracts unchanged. Add an isolated `anvil.assurance` package for canonicalization, release contracts, pack validation, evidence integrity, trust assignment, graph checks, and requirement matching; expose only the two new public models through the existing schema registry. Every integrity decision is deterministic and every expected failure carries a stable code and field path.

**Tech Stack:** Python 3.12+, Pydantic v2, PyYAML safe loading, `packaging` version/specifier semantics, pytest parametrization and fixtures, Ruff, ty, generated JSON Schema draft 2020-12.

---

## File Map

- Create `anvil/assurance/__init__.py`: curated public Assurance API.
- Create `anvil/assurance/errors.py`: stable error codes, paths, and sanitized messages.
- Create `anvil/assurance/canonical.py`: canonical JSON and SHA-256 helpers.
- Create `anvil/assurance/identity.py`: release components and deterministic release identity.
- Create `anvil/assurance/contracts.py`: strict release contract models, YAML loader, and in-memory check-pack registry.
- Create `anvil/assurance/evidence.py`: evidence envelopes, trust policy, content verification, graph validation, and requirement matching.
- Create `tests/assurance/conftest.py`: reusable complete-contract and evidence factories.
- Create `tests/assurance/test_errors.py`: public error contract tests.
- Create `tests/assurance/test_canonical.py`: canonicalization golden vectors.
- Create `tests/assurance/test_identity.py`: release completeness and digest invariants.
- Create `tests/assurance/test_release_contracts.py`: strict envelope and loader tests.
- Create `tests/assurance/test_pack_registry.py`: pack ownership, compatibility, and config tests.
- Create `tests/assurance/test_evidence.py`: evidence shape, identity, trust, and content tests.
- Create `tests/assurance/test_evidence_graph.py`: graph and requirement tests.
- Modify `anvil/contracts.py`: register the new public schemas without moving implementation into the registry.
- Modify `tests/test_contracts.py`: assert export, CLI validation, fixtures, and legacy compatibility.
- Create `fixtures/contracts/assurance-release-contract-valid.yaml`: golden YAML contract.
- Create `fixtures/contracts/assurance-evidence-record-valid.json`: golden evidence record.
- Create `schemas/assurance.anvil.dev.release-contract.v1alpha1.schema.json`: generated contract schema.
- Create `schemas/assurance.anvil.dev.evidence-record.v1alpha1.schema.json`: generated evidence schema.
- Modify `docs/contracts.md`: alpha contract usage and fixture links.
- Modify `docs/schema-versioning.md`: Assurance alpha compatibility rules.
- Modify `docs/artifacts.md`: evidence content and graph semantics.
- Create `docs/assurance-trust.md`: exact L0-L3 claims, verification boundary, and limitations.
- Modify `README.md`: one restrained link to the experimental Assurance foundation.
- Modify `pyproject.toml`: declare `packaging` as a direct runtime dependency.
- Modify `uv.lock`: lock the direct dependency declaration.

### Task 1: Stable Errors And Canonical Primitives

**Files:**
- Create: `anvil/assurance/__init__.py`
- Create: `anvil/assurance/errors.py`
- Create: `anvil/assurance/canonical.py`
- Create: `tests/assurance/test_errors.py`
- Create: `tests/assurance/test_canonical.py`

- [ ] **Step 1: Write failing public-error tests**

```python
import pytest

from anvil.assurance.errors import AssuranceError


def test_assurance_error_exposes_stable_code_and_path() -> None:
    error = AssuranceError(
        "component is missing",
        code="release_identity_incomplete",
        path="$.release.components",
    )

    assert error.code == "release_identity_incomplete"
    assert error.path == "$.release.components"
    assert str(error) == (
        "release_identity_incomplete at $.release.components: component is missing"
    )


def test_assurance_error_rejects_secret_details() -> None:
    with pytest.raises(ValueError, match="details must not contain secret-like keys"):
        AssuranceError(
            "invalid source",
            code="evidence_trust_error",
            path="$.source",
            details={"api_key": "must-not-leak"},
        )
```

- [ ] **Step 2: Write failing canonicalization golden-vector tests**

```python
from anvil.assurance.canonical import canonical_json_bytes, sha256_json


def test_canonical_json_is_utf8_sorted_and_compact() -> None:
    assert canonical_json_bytes({"z": "Привет", "a": [2, 1]}) == (
        '{"a":[2,1],"z":"Привет"}'.encode()
    )


def test_sha256_json_has_prefixed_lowercase_digest() -> None:
    assert sha256_json({"a": 1}) == (
        "sha256:015abd7f5cc57a2dd94b7590f04ad808"
        "4273905ee33ec5cebeae62276a97f862"
    )
```

- [ ] **Step 3: Run the focused tests and confirm import failures**

Run: `uv run pytest -q tests/assurance/test_errors.py tests/assurance/test_canonical.py`

Expected: collection fails because `anvil.assurance` does not exist.

- [ ] **Step 4: Implement the error and canonical APIs**

```python
# anvil/assurance/errors.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SECRET_DETAIL_KEYS = frozenset({"api_key", "authorization", "password", "secret", "token"})


class AssuranceError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        path: str = "$",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        selected_details = dict(details or {})
        if SECRET_DETAIL_KEYS.intersection(key.casefold() for key in selected_details):
            raise ValueError("details must not contain secret-like keys")
        super().__init__(message)
        self.code = code
        self.path = path
        self.details = selected_details

    def __str__(self) -> str:
        return f"{self.code} at {self.path}: {super().__str__()}"
```

```python
# anvil/assurance/canonical.py
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"value is not canonical JSON: {error}") from error
    return rendered.encode("utf-8")


def sha256_bytes(content: bytes, *, prefix: bool = True) -> str:
    digest = hashlib.sha256(content).hexdigest()
    return f"sha256:{digest}" if prefix else digest


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))
```

Export only `AssuranceError`, `canonical_json_bytes`, `sha256_bytes`, and `sha256_json` from `anvil/assurance/__init__.py` at this stage.

- [ ] **Step 5: Run focused quality gates**

Run: `uv run ruff format anvil/assurance tests/assurance && uv run ruff check anvil/assurance tests/assurance && uv run ty check anvil/assurance && uv run pytest -q tests/assurance/test_errors.py tests/assurance/test_canonical.py`

Expected: all checks pass.

- [ ] **Step 6: Commit the primitives**

```bash
git add anvil/assurance tests/assurance
git commit -m "feat(assurance): add canonical integrity primitives"
```

### Task 2: Release Components And Deterministic Identity

**Files:**
- Create: `anvil/assurance/identity.py`
- Create: `tests/assurance/conftest.py`
- Create: `tests/assurance/test_identity.py`
- Modify: `anvil/assurance/__init__.py`

- [ ] **Step 1: Write failing release-identity tests**

Use a `release_components()` fixture containing exactly one `agent_code`, `model_config`, `prompt_bundle`, `tool_schema`, `policy`, and `environment` component. Add parametrized tests proving:

```python
@pytest.mark.parametrize(
    "field,replacement",
    [
        ("name", "changed"),
        ("version", "v999"),
        ("digest", f"sha256:{'f' * 64}"),
    ],
)
def test_release_identity_changes_for_behavior_fields(
    release_components: list[ReleaseComponent], field: str, replacement: str
) -> None:
    baseline = release_identity(release_components)
    changed = [component.model_copy() for component in release_components]
    changed[0] = changed[0].model_copy(update={field: replacement})
    assert release_identity(changed) != baseline
```

Also assert order independence, metadata/path independence, duplicate `(kind, name)` rejection, malformed digest rejection, and missing mandatory kinds raising `AssuranceError(code="release_identity_incomplete", path="$.release.components")`.

- [ ] **Step 2: Run tests and confirm missing identity API**

Run: `uv run pytest -q tests/assurance/test_identity.py`

Expected: collection fails because `anvil.assurance.identity` does not exist.

- [ ] **Step 3: Implement strict components and identity**

```python
class ComponentKind(StrEnum):
    AGENT_CODE = "agent_code"
    MODEL_CONFIG = "model_config"
    PROMPT_BUNDLE = "prompt_bundle"
    TOOL_SCHEMA = "tool_schema"
    POLICY = "policy"
    ENVIRONMENT = "environment"
    ADAPTER = "adapter"
    MEMORY_SCHEMA = "memory_schema"


MANDATORY_COMPONENT_KINDS = frozenset(
    {
        ComponentKind.AGENT_CODE,
        ComponentKind.MODEL_CONFIG,
        ComponentKind.PROMPT_BUNDLE,
        ComponentKind.TOOL_SCHEMA,
        ComponentKind.POLICY,
        ComponentKind.ENVIRONMENT,
    }
)


class ReleaseComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ComponentKind
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


def release_identity(components: Sequence[ReleaseComponent]) -> str:
    validate_release_components(components)
    payload = {
        "components": sorted(
            (
                {
                    "digest": component.digest,
                    "kind": component.kind.value,
                    "name": component.name,
                    "version": component.version,
                }
                for component in components
            ),
            key=lambda item: (item["kind"], item["name"], item["version"], item["digest"]),
        )
    }
    return sha256_json(payload)
```

`validate_release_components()` must reject duplicate `(kind, name)` pairs and report all missing mandatory kinds in sorted order. Metadata is deliberately excluded from the release digest because it is descriptive and may contain machine-local paths; behavior-bearing content is represented by the component digest.

- [ ] **Step 4: Run focused gates**

Run: `uv run ruff format anvil/assurance tests/assurance && uv run ruff check anvil/assurance tests/assurance && uv run ty check anvil/assurance && uv run pytest -q tests/assurance/test_identity.py`

Expected: all tests pass.

- [ ] **Step 5: Commit release identity**

```bash
git add anvil/assurance tests/assurance
git commit -m "feat(assurance): define reproducible release identity"
```

### Task 3: Strict Release Contract Envelope

**Files:**
- Create: `anvil/assurance/contracts.py`
- Create: `tests/assurance/test_release_contracts.py`
- Modify: `anvil/assurance/__init__.py`

- [ ] **Step 1: Write failing envelope tests**

Create a valid payload fixture matching the approved design. Parametrize mutation cases for wrong `apiVersion`, wrong `kind`, every missing required field, unknown fields at each nesting level, duplicate check IDs, duplicate packs, invalid type names, task with both `input` and `inputRef`, task with neither, zero trials, and pass rates outside `[0, 1]`.

The primary round-trip assertion is:

```python
contract = ReleaseContract.model_validate(valid_release_contract_payload)

assert contract.api_version == RELEASE_CONTRACT_SCHEMA_VERSION
assert contract.kind == "ReleaseContract"
assert contract.release_id == release_identity(contract.release.components)
assert contract.model_dump(mode="json", by_alias=True)["apiVersion"] == (
    "assurance.anvil.dev/release-contract/v1alpha1"
)
```

- [ ] **Step 2: Write failing safe-loader and sanitized-error tests**

```python
def test_load_release_contract_rejects_python_yaml_tags(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text("!!python/object/apply:os.system ['echo unsafe']", encoding="utf-8")

    with pytest.raises(AssuranceError) as captured:
        load_release_contract(path)

    assert captured.value.code == "contract_parse_error"
    assert "unsafe" not in str(captured.value)
```

Malformed Pydantic fields must become `contract_schema_error` with a JSONPath-like path derived from the first validation location.

- [ ] **Step 3: Run focused tests and confirm missing contract API**

Run: `uv run pytest -q tests/assurance/test_release_contracts.py`

Expected: collection fails because `ReleaseContract` is not implemented.

- [ ] **Step 4: Implement the alpha envelope**

Define strict Pydantic models for `ContractMetadata`, `ReleaseDefinition`, `ActorDefinition`, `TaskDefinition`, `PackRequirement`, `CheckDefinition`, `EvidencePolicy`, `ReliabilityPolicy`, and `ReleaseContract`. Use explicit aliases for `apiVersion`, `inputRef`, `minimumPassRate`, and future evidence aliases. Use `Literal` discriminators, `Field` bounds, and `model_validator(mode="after")` for cross-field invariants.

```python
class ReleaseContract(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    api_version: Literal[RELEASE_CONTRACT_SCHEMA_VERSION] = Field(alias="apiVersion")
    kind: Literal["ReleaseContract"]
    metadata: ContractMetadata
    release: ReleaseDefinition
    actor: ActorDefinition
    task: TaskDefinition
    packs: list[PackRequirement] = Field(default_factory=list)
    checks: list[CheckDefinition] = Field(default_factory=list)
    evidence: EvidencePolicy = Field(default_factory=EvidencePolicy)
    reliability: ReliabilityPolicy = Field(default_factory=ReliabilityPolicy)

    @property
    def release_id(self) -> str:
        return release_identity(self.release.components)
```

`load_release_contract(path)` must use `yaml.safe_load`, require a mapping, and translate parse/read/schema failures to sanitized `AssuranceError` instances. Registry validation is added in Task 4, so this loader performs only common-envelope validation now.

- [ ] **Step 5: Run focused gates**

Run: `uv run ruff format anvil/assurance tests/assurance && uv run ruff check anvil/assurance tests/assurance && uv run ty check anvil/assurance && uv run pytest -q tests/assurance/test_release_contracts.py tests/assurance/test_identity.py`

Expected: all tests pass.

- [ ] **Step 6: Commit the contract envelope**

```bash
git add anvil/assurance tests/assurance
git commit -m "feat(assurance): add strict release contracts"
```

### Task 4: Explicit Pack And Check Registry

**Files:**
- Modify: `anvil/assurance/contracts.py`
- Create: `tests/assurance/test_pack_registry.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `anvil/assurance/__init__.py`

- [ ] **Step 1: Declare direct version-parser dependency**

Add `"packaging>=25.0"` to `[project].dependencies`, then run `uv lock`.

- [ ] **Step 2: Write failing registry tests**

Use this fake pack config:

```python
class RowCountConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str = Field(min_length=1)
    equals: int = Field(ge=0)


registry = CheckTypeRegistry()
registry.register_pack(
    name="anvil-pack-postgres",
    version="0.1.4",
    check_types={"postgres.row_count.v1": RowCountConfig},
)
```

Assert a compatible contract succeeds. Add tests for `unknown_pack`, `incompatible_pack`, `unknown_check_type`, `check_config_error`, duplicate registry pack names, a check owned by an installed but undeclared pack, and a malicious pack name proving no dynamic import function is called.

- [ ] **Step 3: Run tests and confirm missing registry API**

Run: `uv run pytest -q tests/assurance/test_pack_registry.py`

Expected: tests fail because `CheckTypeRegistry` is missing.

- [ ] **Step 4: Implement registry-owned validation**

```python
@dataclass(frozen=True)
class RegisteredPack:
    name: str
    version: Version
    check_types: Mapping[str, type[BaseModel]]


class CheckTypeRegistry:
    def __init__(self) -> None:
        self._packs: dict[str, RegisteredPack] = {}

    def register_pack(
        self,
        *,
        name: str,
        version: str,
        check_types: Mapping[str, type[BaseModel]],
    ) -> None:
        if name in self._packs:
            raise AssuranceError(
                "pack is already registered",
                code="check_config_error",
                path="$.packs",
                details={"pack": name},
            )
        try:
            selected_version = Version(version)
        except InvalidVersion as error:
            raise AssuranceError(
                "registered pack version is invalid",
                code="check_config_error",
                path="$.packs",
                details={"pack": name},
            ) from error
        self._packs[name] = RegisteredPack(
            name=name,
            version=selected_version,
            check_types=dict(check_types),
        )

    def validate(self, contract: ReleaseContract) -> None:
        declared: dict[str, RegisteredPack] = {}
        for index, requirement in enumerate(contract.packs):
            pack = self._packs.get(requirement.name)
            if pack is None:
                raise AssuranceError(
                    "declared pack is not registered",
                    code="unknown_pack",
                    path=f"$.packs[{index}].name",
                    details={"pack": requirement.name},
                )
            if pack.version not in SpecifierSet(requirement.version):
                raise AssuranceError(
                    "registered pack version is incompatible",
                    code="incompatible_pack",
                    path=f"$.packs[{index}].version",
                    details={"pack": requirement.name},
                )
            declared[pack.name] = pack

        owners = {
            check_type: (pack, model)
            for pack in declared.values()
            for check_type, model in pack.check_types.items()
        }
        for index, check in enumerate(contract.checks):
            owner = owners.get(check.type)
            if owner is None:
                raise AssuranceError(
                    "check type is not owned by a declared compatible pack",
                    code="unknown_check_type",
                    path=f"$.checks[{index}].type",
                    details={"check_type": check.type},
                )
            _, config_model = owner
            try:
                config_model.model_validate(check.config)
            except ValidationError as error:
                raise AssuranceError(
                    "check configuration does not match its registered schema",
                    code="check_config_error",
                    path=f"$.checks[{index}].config",
                    details={"check_type": check.type},
                ) from error
```

`validate()` resolves declared packs from the in-memory map, applies `SpecifierSet(requirement.version)`, maps each registered check type to exactly one owner, requires the owner to be declared, and validates `check.config` with the registered Pydantic model. It never imports a name found in YAML. Extend `load_release_contract(path, registry=None)` so registry validation occurs only when a registry is supplied; a contract containing checks must raise `unknown_check_type` if supplied an empty registry.

- [ ] **Step 5: Run focused gates**

Run: `uv run ruff format anvil/assurance tests/assurance && uv run ruff check anvil/assurance tests/assurance && uv run ty check anvil/assurance && uv run pytest -q tests/assurance/test_pack_registry.py tests/assurance/test_release_contracts.py`

Expected: all tests pass.

- [ ] **Step 6: Commit pack validation**

```bash
git add pyproject.toml uv.lock anvil/assurance tests/assurance
git commit -m "feat(assurance): validate checks through explicit pack registry"
```

### Task 5: Evidence Envelope, Identity, And Trust Assignment

**Files:**
- Create: `anvil/assurance/evidence.py`
- Create: `tests/assurance/test_evidence.py`
- Modify: `anvil/assurance/contracts.py`
- Modify: `anvil/assurance/__init__.py`

- [ ] **Step 1: Write failing evidence shape and identity tests**

Create `evidence_record_payload()` in `tests/assurance/conftest.py` using the approved example. Assert exact `schemaVersion`, strict unknown-field rejection, SHA-256 patterns, timezone-aware `observedAt`, namespaced/versioned evidence type, positive content size, relative POSIX content path, and duplicate/self-parent rejection.

Build evidence IDs with a helper so the golden invariant is explicit:

```python
payload["evidenceId"] = evidence_identity(payload_without_id)
record = EvidenceRecord.model_validate(payload)

assert verify_evidence_identity(record) is None
```

Mutating `observedAt`, source, content metadata, parents, correlations, redaction, release ID, run ID, or contract ID must invalidate the record ID. Mutating bytes without updating `content.sha256` is covered by Task 6.

- [ ] **Step 2: Write failing trust-policy tests**

```python
policy = EvidenceTrustPolicy(
    assignments=[
        TrustAssignment(
            collector="postgres-observer",
            version="0.1.0",
            boundary="separate-read-only-credentials",
            maximum_trust=TrustLevel.L2,
        )
    ]
)

verified = verify_evidence_trust(record, policy)
assert verified.assigned_trust is TrustLevel.L2
```

Add parametrized cases proving L0/L1/L2 claims cannot exceed assignment, L3 requires an L3 assignment, unknown sources fail, source version and boundary are compared, L2/L3 require a non-empty boundary, and producer-controlled record fields alone never establish trust.

- [ ] **Step 3: Run tests and confirm missing evidence API**

Run: `uv run pytest -q tests/assurance/test_evidence.py -k 'identity or trust or schema'`

Expected: collection fails because `anvil.assurance.evidence` does not exist.

- [ ] **Step 4: Implement evidence models and trust verification**

```python
class TrustLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"

    @property
    def rank(self) -> int:
        return int(self.value[1])


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    schema_version: Literal[EVIDENCE_RECORD_SCHEMA_VERSION] = Field(alias="schemaVersion")
    evidence_id: str = Field(alias="evidenceId", pattern=SHA256_PREFIXED_PATTERN)
    run_id: str = Field(alias="runId", min_length=1)
    release_id: str = Field(alias="releaseId", pattern=SHA256_PREFIXED_PATTERN)
    contract_id: str = Field(alias="contractId", min_length=1)
    type: str = Field(pattern=NAMESPACED_TYPE_PATTERN)
    trust_level: TrustLevel = Field(alias="trustLevel")
    subject: str = Field(min_length=1)
    source: EvidenceSource
    observed_at: AwareDatetime = Field(alias="observedAt")
    content: EvidenceContent
    parents: list[str] = Field(default_factory=list)
    correlations: dict[str, str] = Field(default_factory=dict)
    redaction: EvidenceRedaction
```

Implement `evidence_identity(value)` for either an `EvidenceRecord` or a JSON-compatible mapping by dumping aliases in JSON mode when needed, removing `evidenceId`, and hashing canonical JSON. `verify_evidence_identity()` raises `evidence_digest_mismatch` at `$.evidenceId` on mismatch. Reject secret-like correlation keys (`api_key`, `authorization`, `password`, `secret`, `token`) without echoing their values.

Define strict `TrustAssignment`, `EvidenceTrustPolicy`, and immutable `VerifiedTrust`. `verify_evidence_trust()` looks up an exact `(collector, version, boundary)` assignment and rejects claims whose rank exceeds `maximum_trust`; it returns the claimed level as `assigned_trust` after verification rather than silently promoting lower claims.

- [ ] **Step 5: Replace the temporary contract evidence requirement**

Move `EvidenceRequirement` into `evidence.py`, with aliases `minimumTrust` and `minimumCount`, then import it into `contracts.py`. `subject` remains optional because some evidence types apply to the whole run.

- [ ] **Step 6: Run focused gates**

Run: `uv run ruff format anvil/assurance tests/assurance && uv run ruff check anvil/assurance tests/assurance && uv run ty check anvil/assurance && uv run pytest -q tests/assurance/test_evidence.py tests/assurance/test_release_contracts.py`

Expected: all tests pass.

- [ ] **Step 7: Commit evidence trust**

```bash
git add anvil/assurance tests/assurance
git commit -m "feat(assurance): model evidence trust without self elevation"
```

### Task 6: Content Integrity And Store Containment

**Files:**
- Modify: `anvil/assurance/evidence.py`
- Modify: `tests/assurance/test_evidence.py`

- [ ] **Step 1: Write failing content-integrity tests**

Parametrize valid bytes, missing content, wrong size, wrong digest, absolute path, `..` traversal, Windows-style separator, directory target, and a symlink inside the store pointing outside it. The valid assertion is:

```python
verified = verify_evidence_content(record, store_root)

assert verified.path == content_path.resolve()
assert verified.size_bytes == len(content)
```

Expected error mappings:

| Condition | Code | Path |
| --- | --- | --- |
| missing file | `evidence_content_missing` | `$.content.path` |
| path escape/symlink escape | `evidence_path_escape` | `$.content.path` |
| size mismatch | `evidence_digest_mismatch` | `$.content.sizeBytes` |
| digest mismatch | `evidence_digest_mismatch` | `$.content.sha256` |

- [ ] **Step 2: Run the focused tests and verify failures**

Run: `uv run pytest -q tests/assurance/test_evidence.py -k content`

Expected: tests fail because `verify_evidence_content` is missing.

- [ ] **Step 3: Implement containment-before-read verification**

```python
def verify_evidence_content(record: EvidenceRecord, store_root: Path) -> VerifiedContent:
    root = store_root.resolve(strict=True)
    relative = PurePosixPath(record.content.path)
    if relative.is_absolute() or not relative.parts or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise AssuranceError("content path escapes the store", code="evidence_path_escape", path="$.content.path")

    candidate = root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except FileNotFoundError as error:
        raise AssuranceError("evidence content is missing", code="evidence_content_missing", path="$.content.path") from error
    except ValueError as error:
        raise AssuranceError("content path escapes the store", code="evidence_path_escape", path="$.content.path") from error
```

Require a regular file, stream SHA-256 in fixed-size chunks, compare byte count and digest with `hmac.compare_digest`, and never include file content in errors. Return a frozen `VerifiedContent(path, size_bytes, sha256)`.

- [ ] **Step 4: Add composed record verification**

Implement:

```python
def verify_evidence_record(
    record: EvidenceRecord,
    *,
    expected_release_id: str,
    trust_policy: EvidenceTrustPolicy,
    store_root: Path,
) -> VerifiedEvidence:
    verify_evidence_identity(record)
    if not hmac.compare_digest(record.release_id, expected_release_id):
        raise AssuranceError(
            "evidence belongs to a different release",
            code="evidence_schema_error",
            path="$.releaseId",
        )
    trust = verify_evidence_trust(record, trust_policy)
    content = verify_evidence_content(record, store_root)
    return VerifiedEvidence(
        record=record,
        assigned_trust=trust.assigned_trust,
        content=content,
    )
```

It verifies evidence identity, exact release binding, trust assignment, and content integrity in that order. Release mismatch uses `evidence_schema_error` at `$.releaseId`. `VerifiedEvidence` contains the original record, assigned trust, and verified content.

- [ ] **Step 5: Run focused gates**

Run: `uv run ruff format anvil/assurance tests/assurance && uv run ruff check anvil/assurance tests/assurance && uv run ty check anvil/assurance && uv run pytest -q tests/assurance/test_evidence.py`

Expected: all tests pass.

- [ ] **Step 6: Commit content integrity**

```bash
git add anvil/assurance/evidence.py tests/assurance/test_evidence.py
git commit -m "feat(assurance): verify evidence store integrity"
```

### Task 7: Evidence Graph And Requirement Matching

**Files:**
- Create: `tests/assurance/test_evidence_graph.py`
- Modify: `anvil/assurance/evidence.py`
- Modify: `anvil/assurance/__init__.py`

- [ ] **Step 1: Write failing graph tests**

Build a deterministic three-record chain and assert `validate_evidence_graph(records)` returns records in topological order with parents before children. Add tests for duplicate evidence IDs, duplicate parents, self-parent, dangling parent, two-node cycle, longer cycle, and input-order independence.

```python
ordered = validate_evidence_graph([post_state, trace, pre_state])
assert [record.evidence_id for record in ordered] == [
    pre_state.evidence_id,
    trace.evidence_id,
    post_state.evidence_id,
]
```

Dangling parents use `evidence_schema_error` at `$.parents`; cycles use `evidence_graph_cycle` at `$.parents`.

- [ ] **Step 2: Write failing requirement tests**

Parametrize the trust matrix so L0 satisfies only L0, L1 satisfies L0/L1, L2 satisfies L0/L1/L2, and L3 satisfies all levels. Also test exact type match, optional/exact subject match, `minimumCount`, duplicate records not double-counted, and unverified `EvidenceRecord` objects being rejected by the API type/runtime guard.

```python
match = match_evidence_requirement(requirement, verified_records)
assert match.satisfied is True
assert match.evidence_ids == (record.evidence_id,)
```

- [ ] **Step 3: Run focused tests and verify failures**

Run: `uv run pytest -q tests/assurance/test_evidence_graph.py`

Expected: tests fail because graph and matching functions are missing.

- [ ] **Step 4: Implement deterministic graph validation**

Use an ID-indexed mapping and Kahn topological sort with a lexicographically sorted ready queue. Reject duplicates before building edges. The function returns a tuple of records and does not mutate input.

- [ ] **Step 5: Implement verified-only requirement matching**

```python
@dataclass(frozen=True)
class EvidenceRequirementMatch:
    requirement: EvidenceRequirement
    evidence_ids: tuple[str, ...]

    @property
    def satisfied(self) -> bool:
        return len(self.evidence_ids) >= self.requirement.minimum_count
```

`match_evidence_requirement()` accepts only `Sequence[VerifiedEvidence]`, filters exact type, optional subject, and monotonic assigned-trust rank, then sorts unique IDs. Add `match_evidence_requirements()` preserving contract requirement order. Do not calculate a release verdict in this foundation.

- [ ] **Step 6: Run focused gates**

Run: `uv run ruff format anvil/assurance tests/assurance && uv run ruff check anvil/assurance tests/assurance && uv run ty check anvil/assurance && uv run pytest -q tests/assurance/test_evidence_graph.py tests/assurance/test_evidence.py`

Expected: all tests pass.

- [ ] **Step 7: Commit graph and requirements**

```bash
git add anvil/assurance tests/assurance
git commit -m "feat(assurance): validate evidence graphs and requirements"
```

### Task 8: Public Schemas, Golden Fixtures, And CLI Compatibility

**Files:**
- Modify: `anvil/contracts.py`
- Modify: `tests/test_contracts.py`
- Create: `fixtures/contracts/assurance-release-contract-valid.yaml`
- Create: `fixtures/contracts/assurance-evidence-record-valid.json`
- Create: `schemas/assurance.anvil.dev.release-contract.v1alpha1.schema.json`
- Create: `schemas/assurance.anvil.dev.evidence-record.v1alpha1.schema.json`

- [ ] **Step 1: Write failing schema-registry tests**

Extend `CONTRACT_SCHEMAS` with:

```python
"assurance.anvil.dev/release-contract/v1alpha1": (
    "assurance.anvil.dev.release-contract.v1alpha1.schema.json"
),
"assurance.anvil.dev/evidence-record/v1alpha1": (
    "assurance.anvil.dev.evidence-record.v1alpha1.schema.json"
),
```

Extend fixture tests to parse both models, assert aliases, and assert fixture release/evidence IDs verify. Add CLI tests:

```python
result = runner.invoke(
    app,
    [
        "schema",
        "validate",
        "fixtures/contracts/assurance-release-contract-valid.yaml",
        "--schema",
        "assurance.anvil.dev/release-contract/v1alpha1",
    ],
)
assert result.exit_code == 0
```

Evidence JSON must auto-detect `schemaVersion`. Existing snake-case `schema_version` auto-detection tests must remain unchanged.

- [ ] **Step 2: Run contract tests and verify registry failures**

Run: `uv run pytest -q tests/test_contracts.py`

Expected: tests fail because schemas and registry entries are absent.

- [ ] **Step 3: Register public Assurance models additively**

Import `ReleaseContract`, `EvidenceRecord`, and their constants into `anvil/contracts.py`. Add two `SchemaContract` entries. Change auto-detection to consider `schema_version`, then `schemaVersion`, then `apiVersion`, without changing precedence. Route the release contract to `_read_yaml_payload`; all JSON contracts, including evidence, use `_read_json_payload`.

Ensure `contract_schema()` calls `model_json_schema(mode="validation", by_alias=True)` so public camel-case names appear in generated schemas.

- [ ] **Step 4: Add golden fixtures**

Write the approved six-component release contract. Use an empty `checks` and `packs` list in the public fixture so schema validation does not depend on an installed domain pack. Include two evidence requirements: an L2 state snapshot with subject and an L1 agent trace without subject.

Write evidence bytes under a temporary store only in unit tests; the JSON fixture validates the envelope and ID but deliberately references a sample content address that schema validation does not dereference.

- [ ] **Step 5: Export and check in schemas**

Run: `uv run anvil schema export --out schemas`

Expected: both new files are printed and all existing schema files remain semantically unchanged except deliberate `by_alias=True` normalization. If existing files differ, inspect and avoid unrelated churn by limiting alias behavior to the new contracts or confirming current exports are already alias-based.

- [ ] **Step 6: Run schema and legacy regression tests**

Run: `uv run pytest -q tests/test_contracts.py tests/test_scenario_loader.py tests/test_trace_schema.py`

Expected: all tests pass, including every legacy contract fixture.

- [ ] **Step 7: Commit public contracts**

```bash
git add anvil/contracts.py tests/test_contracts.py fixtures/contracts schemas
git commit -m "feat(assurance): publish alpha contract schemas"
```

### Task 9: Trust, Artifact, And Compatibility Documentation

**Files:**
- Create: `docs/assurance-trust.md`
- Modify: `docs/contracts.md`
- Modify: `docs/schema-versioning.md`
- Modify: `docs/artifacts.md`
- Modify: `README.md`
- Modify: `tests/test_contracts.py`

- [ ] **Step 1: Write failing documentation-contract assertions**

Add assertions that README links `docs/assurance-trust.md`, contract docs link both fixtures and schemas, schema-versioning docs contain `v1alpha1` compatibility rules, artifact docs explain local content-addressed evidence, and trust docs contain all four levels plus the exact phrase `Trust describes observation provenance, not whether the agent is safe.`

- [ ] **Step 2: Run docs test and verify failure**

Run: `uv run pytest -q tests/test_contracts.py::test_contract_docs_link_schema_export_and_conformance_fixtures`

Expected: FAIL because Assurance documentation links are absent.

- [ ] **Step 3: Document the stable boundary without overclaiming**

`docs/assurance-trust.md` must state:

- L0-L3 definitions and examples;
- records claim trust, trusted configuration assigns it;
- L2 is independently observed but not tamper-proof;
- L3 adds authenticated/attested provenance but does not prove host, collector, trust root, provider, or environment integrity;
- current traces remain L0/L1 unless separately observed;
- evidence remains local and redacted before persistence;
- the foundation has no runner, collector, oracle, verdict, signing, or hosted control plane yet.

`docs/contracts.md` must show `uv run anvil schema validate fixtures/contracts/assurance-release-contract-valid.yaml --schema assurance.anvil.dev/release-contract/v1alpha1` for YAML and `uv run anvil schema validate fixtures/contracts/assurance-evidence-record-valid.json` for auto-detected evidence JSON. `docs/schema-versioning.md` must state unknown-field rejection and when `v1alpha2`/stable `v1` are required. `docs/artifacts.md` must explain `evidenceId` versus `content.sha256`, normalized relative paths, parent graphs, and verification order.

README gets only a short `Experimental Assurance foundation` paragraph and a link; do not add a second product narrative or claim production readiness.

- [ ] **Step 4: Run documentation tests**

Run: `uv run pytest -q tests/test_contracts.py`

Expected: all tests pass.

- [ ] **Step 5: Commit documentation**

```bash
git add README.md docs tests/test_contracts.py
git commit -m "docs(assurance): define evidence trust boundary"
```

### Task 10: Full Verification, Review, PR, And Release Train

**Files:**
- Modify only files required by review findings or release-version synchronization.

- [ ] **Step 1: Run the complete local gate**

Run:

```bash
uv run ruff format --check
uv run ruff check
uv run ty check
uv run pytest -q
```

Expected: formatting, lint, and type checks pass; at least 468 tests plus the new Assurance tests pass; repository coverage remains at or above 90%.

- [ ] **Step 2: Run package and schema reproducibility checks**

Run:

```bash
uv build
uv run anvil schema export --out /tmp/agent-anvil-assurance-schemas
git diff --exit-code -- schemas
```

Expected: sdist and wheel build; exported checked-in schemas remain identical; worktree differs only by intentional source changes.

- [ ] **Step 3: Perform focused security and compatibility review**

Review specifically for YAML code execution, registry-driven dynamic imports, secret-bearing error messages, path/symlink escapes, claimed-trust self-elevation, digest comparison mistakes, graph denial-of-service from recursion, and accidental changes to `anvil run`, `report`, scenario, trace, results, or leaderboard contracts. Fix each validated finding with a failing regression test and a separate commit.

- [ ] **Step 4: Push and open a ready PR**

```bash
git push -u origin codex/assurance-foundation-design
gh pr create --base main --head codex/assurance-foundation-design \
  --title "feat: add Assurance release and evidence foundations" \
  --body-file /tmp/agent-anvil-assurance-pr.md
```

The PR body must list scope, explicit non-goals, trust model, compatibility statement, exact test commands, and the follow-on PostgreSQL design.

- [ ] **Step 5: Wait for every required GitHub check**

Run: `gh pr checks --watch <PR_NUMBER>`

Expected: CI on Python 3.12/3.14, coverage, schema checks, CodeQL/security checks, and Agent Anvil self-eval all pass. Do not merge on pending, skipped-required, or failed checks.

- [ ] **Step 6: Merge and verify main**

Run: `gh pr merge <PR_NUMBER> --squash --delete-branch`

Then update the main worktree with `git pull --ff-only`, confirm the merge commit, and verify the default branch workflows finish successfully.

- [ ] **Step 7: Publish synchronized versions**

First close the existing v0.2.73 release gap at commit `f55e4e9` if the tag is still absent. Then publish the Assurance foundation as the next patch release by updating `pyproject.toml`, regenerating `uv.lock`, committing the version bump through a release PR, creating the matching GitHub release/tag only after green CI, updating the Marketplace wrapper's default core pin in its own granular PR/release, and finally replacing all floating documentation pins with the released versions.

Expected: package version, core Git tag/release, Marketplace wrapper pin/tag, README examples, and checked-in action references are mutually consistent.

## Self-Review Results

- **Spec coverage:** Tasks 1-9 cover all foundation scope and acceptance criteria: strict envelopes, complete release identity, explicit pack registry, L0-L3 assignment, evidence/content integrity, graph validation, monotonic requirements, public schemas/fixtures, compatibility, trust/privacy documentation, and regression gates. PostgreSQL execution, collectors, verdicts, faults, signing, and dashboards remain excluded.
- **Placeholder scan:** The plan contains no TODO, TBD, generic “handle errors,” unspecified “write tests” steps, or incomplete function bodies. The only ellipsis token is Python's valid `tuple[str, ...]` variadic tuple type.
- **Type consistency:** Public names are consistently `ReleaseContract`, `ReleaseComponent`, `CheckTypeRegistry`, `EvidenceRecord`, `EvidenceTrustPolicy`, `TrustAssignment`, `VerifiedEvidence`, `EvidenceRequirement`, and `AssuranceError`. Public aliases match the approved camel-case wire format. Release IDs are prefixed SHA-256; content digests are unprefixed lowercase SHA-256.
