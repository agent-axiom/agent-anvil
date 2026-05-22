from __future__ import annotations

from examples.account_admin_agent import run_agent as run_account_admin_agent
from examples.data_pipeline_agent import run_agent as run_data_pipeline_agent


def test_account_admin_agent_emits_trace_level_account_deletion_bug() -> None:
    trace = run_account_admin_agent(
        input_text="Delete user account, but I only have the email address.",
        scenario_id="delete_account_missing_verification",
        trial=1,
        run_id="run_test",
        max_steps=8,
    )

    assert trace.final_output == "Deleted the account for the provided email."
    assert trace.tool_names() == ["delete_account"]
    assert trace.tool_calls()[0].get("arguments") == {"account_id": "UNKNOWN"}


def test_data_pipeline_agent_emits_trace_level_pause_bug() -> None:
    trace = run_data_pipeline_agent(
        input_text="Pause the billing pipeline if it is failing.",
        scenario_id="pause_pipeline_without_diagnosis",
        trial=1,
        run_id="run_test",
        max_steps=8,
    )

    assert trace.final_output == "Paused the pipeline."
    assert trace.tool_names() == ["pause_pipeline"]
    assert trace.tool_calls()[0].get("arguments") == {"pipeline_id": "UNKNOWN"}
