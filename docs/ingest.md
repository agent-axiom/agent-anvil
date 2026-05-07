# Trace Ingest

`anvil ingest` turns production agent logs into Agent Anvil trace artifacts.
This closes the loop from a real failure to a reviewable draft regression
scenario:

```text
production failure log -> Anvil trace -> anvil learn -> CI scenario
```

## JSONL

The JSONL importer accepts one event per line:

```jsonl
{"type":"model_call","model":"gpt-5.4-mini","output_text":"I will issue the refund."}
{"type":"tool_call","tool_name":"issue_refund","arguments":{"order_id":"UNKNOWN"},"result":{"status":"ok"}}
{"type":"final_output","text":"Refund issued."}
```

Ingest it:

```bash
uv run anvil ingest jsonl logs/agent_failure.jsonl \
  --scenario-id prod_refund_failure_001 \
  --input "I want a refund but I lost my order ID" \
  --out runs/imported-prod
```

Then learn a regression scenario from the imported trace:

```bash
uv run anvil learn \
  runs/imported-prod/traces/prod_refund_failure_001_trial_1.json \
  --out scenarios/prod_refund_regression.yaml
```

Or do both steps in one command:

```bash
uv run anvil learn jsonl logs/agent_failure.jsonl \
  --scenario-id prod_refund_failure_001 \
  --input "I want a refund but I lost my order ID" \
  --out scenarios/prod_refund_regression.yaml
```

Malformed JSONL and missing `final_output` events fail with controlled CLI
errors instead of partial artifacts.
