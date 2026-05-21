from __future__ import annotations

import pytest
from pydantic import ValidationError

from anvil.benchmark import BenchmarkManifest, load_benchmark_manifest


def test_load_benchmark_manifest(tmp_path):
    manifest_path = tmp_path / "paper.yaml"
    manifest_path.write_text(
        """
name: paper_benchmark
description: Trace-aware eval benchmark.
suites:
  - experiments/scenarios/refund.yaml
output:
  json: docs/paper/results.json
  markdown: docs/paper/results.md
""",
        encoding="utf-8",
    )

    manifest = load_benchmark_manifest(manifest_path)

    assert manifest.name == "paper_benchmark"
    assert manifest.suites == [tmp_path / "experiments/scenarios/refund.yaml"]
    assert manifest.output.json_path == tmp_path / "docs/paper/results.json"
    assert manifest.output.markdown == tmp_path / "docs/paper/results.md"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "name": "paper_benchmark",
            "suites": [],
        },
        {
            "name": "paper_benchmark",
            "suites": ["experiments/scenarios/refund.yaml"],
            "unknown": True,
        },
        {
            "name": "paper_benchmark",
            "suites": ["experiments/scenarios/refund.yaml"],
            "output": {"json": "docs/paper/results.json", "extra": True},
        },
    ],
)
def test_benchmark_manifest_rejects_invalid_payload(payload):
    with pytest.raises(ValidationError):
        BenchmarkManifest.model_validate(payload)
