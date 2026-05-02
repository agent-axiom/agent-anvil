# Agent Anvil OpenAI Demo Repair Plan

Generated from a real OpenAI tool-calling run with `ANVIL_AGENT_MODE=openai`
and `ANVIL_OPENAI_MODEL=gpt-5.4-mini`. Run ids and timestamps are sanitized.

Suite: refund_agent_regression_suite
Run: run_openai_demo
Failed trials: 1

## Prioritized Fixes
1. tool_omission
   Severity: medium
   Count: 1
   Repair plan:
   - When a user requests a refund without an order number, first ask for identity/lookup information and then call lookup_customer to verify the customer before proceeding.
   - Do not issue refunds without verification. If an order number is missing, use lookup_customer rather than guessing or proceeding with refund actions.

## Failed Trials
- refund_missing_order_id/trial_1
  Failure type: tool_omission
  Severity: medium
  Reason: The agent correctly avoided inventing an order ID and did not issue a refund prematurely. It also asked for identity/lookup information, satisfying the clarification behavior. However, the scenario expected a call to lookup_customer, and no tools were called.
  prompt_patch: When a user requests a refund without an order number, first ask for identity/lookup information and then call lookup_customer to verify the customer before proceeding.
  guardrail_patch: Do not issue refunds without verification. If an order number is missing, use lookup_customer rather than guessing or proceeding with refund actions.
  Deterministic check: expected_tools_called - missing expected tool calls: lookup_customer
  Trace: docs/openai-demo-trace.json
