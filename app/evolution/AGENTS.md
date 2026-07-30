# Evolution constraints

- Production code, policy, permissions and high-risk Skill evolution is offline-only. Explicit low-authority Memory CRUD and bounded utility updates for Memory/validated low-risk Skills run online.
- Every harness component has an immutable core contract: identity, responsibility, authority, input/output semantics and fail-safe behavior. Improvement may change bounded data or strategies, never remove the mechanism that makes the component useful.
- Never expose sealed tests, credentials, evaluators, audit code or promotion gates to a candidate worktree.
- Candidate generators may propose changes; only deterministic paired evaluation can promote.
- Mutable and immutable paths must never share one proposal. Immutable control-plane changes always require trusted human approval, even when optional approval is disabled for mutable candidates.
- High-risk slice regressions always block promotion.
- A candidate that fails any affected component's core-contract evaluation cannot be promoted, regardless of aggregate task gain.
- Missing official A-Evolve, GEPA or Adaptive Harness is `unavailable`; do not substitute a local optimizer.
- Release refs and audit records are append/freeze operations; rollback targets only frozen releases.
