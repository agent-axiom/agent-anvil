from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from anvil.cli import app
from anvil.fix import generate_fix_patch
from anvil.grading import HeuristicSemanticGrader
from anvil.runner import run_suite


def test_generate_fix_patch_suggests_prompt_and_tool_description_changes(
    scenario_file: Path,
    tmp_path: Path,
) -> None:
    result = run_suite(
        scenario_file,
        runs_dir=tmp_path / "runs",
        trials_override=1,
        semantic_grader=HeuristicSemanticGrader(),
    )
    prompt = tmp_path / "system_prompt.md"
    prompt.write_text(
        "You are a refund agent.\n\n`issue_refund`: Issues a refund to a customer.\n",
        encoding="utf-8",
    )
    tools = tmp_path / "tools.py"
    tools.write_text(
        '"description": "Issues a refund to a customer.",\n',
        encoding="utf-8",
    )
    out = tmp_path / "anvil-fix.patch"

    patch_path = generate_fix_patch(
        result.run_dir, prompt_path=prompt, tools_path=tools, out_path=out
    )

    patch = patch_path.read_text(encoding="utf-8")
    assert patch.startswith("--- ")
    assert "Only call after lookup_order confirms the order exists" in patch
    assert "-`issue_refund`: Issues a refund to a customer." in patch
    assert '+"description": "Only call after lookup_order confirms the order exists' in patch
    assert prompt.read_text(encoding="utf-8").startswith("You are a refund agent.")


def test_cli_fix_writes_patch_file(scenario_file: Path, tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    CliRunner().invoke(
        app,
        [
            "run",
            str(scenario_file),
            "--runs-dir",
            str(runs_dir),
            "--trials",
            "1",
            "--offline",
        ],
    )
    prompt = tmp_path / "system_prompt.md"
    prompt.write_text("`issue_refund`: Issues a refund to a customer.\n", encoding="utf-8")
    tools = tmp_path / "tools.py"
    tools.write_text('"description": "Issues a refund to a customer.",\n', encoding="utf-8")
    out = tmp_path / "fix.patch"

    result = CliRunner().invoke(
        app,
        [
            "fix",
            str(runs_dir / "latest"),
            "--prompt",
            str(prompt),
            "--tools",
            str(tools),
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0
    assert f"Wrote {out}" in result.stdout
    assert out.exists()
