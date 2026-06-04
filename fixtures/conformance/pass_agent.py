from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> None:
    payload = json.loads(sys.stdin.read())
    env_marker = os.environ.get("ANVIL_CONFORMANCE_MARKER", "unset")
    sys.stdout.write(
        json.dumps(
            {
                "type": "model_call",
                "model": "external-conformance-fixture",
                "input": payload["input"],
                "output_text": f"cwd={Path.cwd().name}; env={env_marker}",
                "tool_calls": [],
            }
        )
        + "\n"
    )
    sys.stdout.write(
        json.dumps(
            {
                "type": "final_output",
                "text": f"external agent ok; cwd={Path.cwd().name}; env={env_marker}",
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
