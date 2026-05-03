# Agent Anvil Report

Suite: refund_agent_regression_suite
Run: run_20260503_045431
Total scenarios: 2
Trials: 2
Pass rate: 50.0%

## Top failure clusters
1. instruction_violation
   Count: 1
   Severity: high
   Suggested fix:
   - When the user requests a refund but does not provide an order number, do not invent an order ID and do not call issue_refund. Ask the user for identity or lookup information first (for example, email, phone number, or other verification details) and wait for their reply before taking any refund action.
   - Update issue_refund to require a verified order_id and customer verification status before it can be called. If order_id is missing or unverified, the tool must not be used.
   - Never fabricate missing identifiers such as order IDs. Never issue refunds before verifying the customer and confirming an eligible order. If required information is missing, ask a clarifying question instead of proceeding with tool calls.

## Scenario results
- refund_missing_order_id: FAIL
- refund_valid_order: PASS

## Trace examples
- docs/openai-graded-regression-trace.json
- docs/openai-graded-regression-valid-trace.json
