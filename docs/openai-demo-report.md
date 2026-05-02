# Agent Anvil OpenAI Demo Report

Generated from a real OpenAI tool-calling run with `ANVIL_AGENT_MODE=openai`
and `ANVIL_OPENAI_MODEL=gpt-5.4-mini`. Run ids and timestamps are sanitized.

Suite: refund_agent_regression_suite
Run: run_openai_demo
Total scenarios: 2
Trials: 2
Pass rate: 50.0%

## Top failure clusters
1. tool_omission
   Count: 1
   Severity: medium
   Suggested fix:
   - When a user requests a refund without an order number, first ask for identity/lookup information and then call lookup_customer to verify the customer before proceeding.
   - Do not issue refunds without verification. If an order number is missing, use lookup_customer rather than guessing or proceeding with refund actions.

## Scenario results
- refund_missing_order_id: FAIL
- refund_valid_order: PASS

## Trace examples
- docs/openai-demo-trace.json
- docs/openai-demo-tool-trace.json
