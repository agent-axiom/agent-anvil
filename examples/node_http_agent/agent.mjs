import { readFileSync } from "node:fs";
import process, { stdin, stdout } from "node:process";
import { fileURLToPath } from "node:url";

const ORDER_ID_RE = /\bORD-\d+\b/;
const MODEL_NAME = "node-demo-agent";

export function handleAnvil(payload) {
  const inputText = String(payload.input ?? "");
  const orderId = extractOrderId(inputText);

  if (!orderId) {
    return {
      status: "completed",
      events: [
        {
          type: "model_call",
          model: MODEL_NAME,
          input: inputText,
          output_text: "I need an order ID before looking up refund eligibility.",
          tool_calls: [],
        },
        {
          type: "final_output",
          text: "Can you provide the order ID so I can verify it before any refund?",
        },
      ],
    };
  }

  return {
    status: "completed",
    events: [
      {
        type: "model_call",
        model: MODEL_NAME,
        input: inputText,
        output_text: `I will look up ${orderId} before any refund action.`,
        tool_calls: [{ name: "lookup_order", arguments: { order_id: orderId } }],
      },
      {
        type: "tool_call",
        tool_name: "lookup_order",
        arguments: { order_id: orderId },
        result: { order_id: orderId, status: "found", verified: true },
      },
      {
        type: "final_output",
        text: `Order ${orderId} is verified. No refund was issued by this demo agent.`,
      },
    ],
  };
}

function extractOrderId(inputText) {
  return inputText.match(ORDER_ID_RE)?.[0] ?? null;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const payload = JSON.parse(readFileSync(stdin.fd, "utf8") || "{}");
  stdout.write(`${JSON.stringify(handleAnvil(payload))}\n`);
}
