# Evolution constraints

- Evolution is offline-only and may never mutate the active clinical workspace directly.
- Never expose sealed tests, credentials, evaluators, audit code or promotion gates to a candidate worktree.
- Candidate generators may propose changes; only deterministic paired evaluation can promote.
- Mutable and immutable paths must never share one proposal. Immutable control-plane changes always require trusted human approval, even when optional approval is disabled for mutable candidates.
- High-risk slice regressions always block promotion.
- Missing official A-Evolve, GEPA or Adaptive Harness is `unavailable`; do not substitute a local optimizer.
- Release refs and audit records are append/freeze operations; rollback targets only frozen releases.
