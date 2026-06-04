from __future__ import annotations

import json
import sys

payload = json.loads(sys.stdin.read())
sys.stdout.write(
    json.dumps(
        {
            "type": "model_call",
            "model": "external-conformance-fixture",
            "input": payload["input"],
            "output_text": "I forgot to emit final_output.",
            "tool_calls": [],
        }
    )
    + "\n"
)
