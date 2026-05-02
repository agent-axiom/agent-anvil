# Agent Anvil Patched Demo Report

This is the "after" side of the repair loop. The original offline demo calls
`issue_refund(order_id="UNKNOWN")`; the patched support agent asks for lookup
identity before any destructive tool call.

Suite: refund_agent_patched_suite
Run: run_patched_demo
Total scenarios: 2
Trials: 2
Pass rate: 100.0%

## Top failure clusters
No failures clustered.

## Scenario results
- refund_missing_order_id: PASS
- refund_valid_order: PASS

## Trace examples
- docs/patched-demo-trace.json
