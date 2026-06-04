# HTTP Agent Endpoint v1

## Goal

Let Agent Anvil evaluate already-running agents over HTTP without forcing users
to write subprocess JSONL glue.

## Scope

- Extend external agent config with `protocol: http`, `url`, and optional
  `headers`.
- POST the same scenario payload used by the subprocess protocol.
- Accept JSON responses in either `steps` + `final_output` form or `events`
  form with a `final_output` event.
- Convert HTTP status errors, network errors, timeouts, and malformed responses
  into controlled failed traces with `agent_protocol_error`.
- Document the protocol and update exported scenario schema contracts.

## Out Of Scope

- Auth helpers beyond static headers and environment expansion.
- Streaming HTTP/SSE.
- Hosted agent registry.
