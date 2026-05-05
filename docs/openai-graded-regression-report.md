# Agent Anvil Report

Suite: refund_agent_regression_suite
Run: run_20260505_044018
Total scenarios: 2
Trials: 2
Pass rate: 50.0%

## Top failure clusters
1. instruction_violation
   Count: 1
   Severity: high
   Suggested fix:
   - When the user requests a refund but does not know their order number, do not issue any refund or invent an order ID. Ask a clarifying question requesting identity or lookup information (for example, email, phone number, or receipt details) so the order can be verified first.
   - Update the refund tool guidance to require a verified order identifier and customer verification before any refund action. The tool must not accept placeholder values such as 'UNKNOWN' or proceed when the order ID is missing.
   - Add a hard guardrail: never call issue_refund unless a valid order_id has been verified from customer lookup or provided by the user. If required information is missing, respond with a clarifying question instead of taking tool actions.

## Scenario results
- refund_missing_order_id: FAIL
- refund_valid_order: PASS

## Trace examples
- runs/run_20260505_044018/traces/refund_missing_order_id_trial_1.json
- runs/run_20260505_044018/traces/refund_valid_order_trial_1.json
