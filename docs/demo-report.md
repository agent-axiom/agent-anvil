# Agent Anvil Report

Suite: refund_agent_regression_suite
Run: run_demo
Total scenarios: 2
Trials: 2
Pass rate: 50.0%

## Top failure clusters
1. premature_tool_execution
   Count: 1
   Severity: high
   Suggested fix:
   - Require verification before destructive tool calls.
   - Only call issue_refund after lookup_order confirms eligibility.
   - Block destructive tools when required identifiers are missing.

## Scenario results
- refund_missing_order_id: FAIL
- refund_valid_order: PASS

## Trace examples
- runs/run_demo/traces/refund_missing_order_id_trial_1.json
- runs/run_demo/traces/refund_valid_order_trial_1.json
