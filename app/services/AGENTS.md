# Service constraints

- Long-term memory defaults to proposed and sensitive.
- Runtime memory is mutable, low-authority user context; it may never represent or override system constraints, safety policy, business red lines, permissions or tool policy.
- Memory records and bounded utility evolve online, but the CRUD lifecycle, provenance, confirmation, conflict handling, clinical protection and user correction/deletion guarantees are immutable control-plane mechanisms.
- Treat the component contract as the boundary: mutable records are Memory's working data; the ability and rules to create, read, update and delete them are Memory's protected core.
- Deduplicate before write and preserve source/status.
- Candidate skills cannot be enabled without validation.
- Never store reusable patient diagnoses as experience memory.
