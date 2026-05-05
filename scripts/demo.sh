#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DEMO_DIR="${ANVIL_DEMO_DIR:-runs/demo}"
PATCH_DIR="$DEMO_DIR/patches"
REPORT_DIR="$DEMO_DIR/reports"
SCENARIO_DIR="$DEMO_DIR/scenarios"
TRACE_DIR="$DEMO_DIR/traces"
mkdir -p "$PATCH_DIR" "$REPORT_DIR" "$SCENARIO_DIR" "$TRACE_DIR"

echo "== Agent Anvil 30-second demo =="
echo "1. Catch an intentional refund-agent regression"
set +e
uv run anvil run scenarios/refund_agent.yaml --offline --agent-mode offline --trials 1
status=$?
set -e
if [[ "$status" -ne 1 ]]; then
  echo "Expected refund regression run to exit 1, got $status" >&2
  exit 1
fi

echo
echo "2. Generate repair plan"
uv run anvil repair runs/latest

echo
echo "3. Generate reviewable patch diff"
uv run anvil fix runs/latest \
  --prompt examples/support_agent/system_prompt.md \
  --tools examples/support_agent/tools.py \
  --out "$PATCH_DIR/anvil-fix.patch"

echo
echo "4. Learn a permanent regression scenario from the bad trace"
uv run anvil learn runs/latest/traces/refund_missing_order_id_trial_1.json \
  --out "$SCENARIO_DIR/learned_refund_regression.yaml"

echo
echo "5. Render a PR-ready regression comment"
uv run anvil pr-comment runs/latest --out "$DEMO_DIR/agent-anvil-pr-comment.md"

echo
echo "6. Audit exported MCP tool schemas"
uv run anvil mcp audit docs/fixtures/mcp-tools.json \
  --out "$SCENARIO_DIR/mcp_tool_safety.yaml" \
  --report "$REPORT_DIR/mcp-audit.md"

echo
echo "7. Export an OpenAI-style trace JSON"
uv run anvil trace export runs/latest --format openai-trace --out "$TRACE_DIR/openai-trace.json"

echo
echo "Artifacts:"
echo "- runs/latest/report.md"
echo "- runs/latest/repair_plan.md"
echo "- $PATCH_DIR/anvil-fix.patch"
echo "- $SCENARIO_DIR/learned_refund_regression.yaml"
echo "- $DEMO_DIR/agent-anvil-pr-comment.md"
echo "- $SCENARIO_DIR/mcp_tool_safety.yaml"
echo "- $REPORT_DIR/mcp-audit.md"
echo "- $TRACE_DIR/openai-trace.json"
