# API constraints

- Every user-owned run, artifact, memory and conversation must check ownership.
- Public events must not include chain-of-thought, secrets or full raw provider payloads.
- Long-running work returns 202 and streams state through SSE/WebSocket.
- Keep legacy auth/conversation APIs until a migration is supplied.
