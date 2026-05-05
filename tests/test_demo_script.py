from __future__ import annotations

from pathlib import Path


def test_demo_script_runs_full_improvement_flywheel() -> None:
    script = Path("scripts/demo.sh")
    text = script.read_text(encoding="utf-8")

    assert script.exists()
    assert script.stat().st_mode & 0o111
    assert "anvil run scenarios/refund_agent.yaml --offline --agent-mode offline --trials 1" in text
    assert "anvil repair runs/latest" in text
    assert "anvil fix runs/latest" in text
    assert "anvil learn runs/latest/traces/refund_missing_order_id_trial_1.json" in text
    assert "anvil pr-comment runs/latest" in text
    assert "anvil mcp audit docs/fixtures/mcp-tools.json" in text


def test_readme_links_one_command_demo() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "scripts/demo.sh" in readme
    assert "One-command demo" in readme
