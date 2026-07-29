# Observability constraints

- Export only identifiers, status, latency, counts and token aggregates.
- Never export prompts, answers, tool arguments, patient text, credentials or raw exceptions.
- A missing exporter is degraded/unavailable, never silently replaced.
- Changes to the export allowlist require a privacy regression test.
