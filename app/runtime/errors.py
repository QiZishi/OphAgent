class RuntimeErrorBase(Exception):
    code = "runtime_error"


class CapabilityUnavailable(RuntimeErrorBase):
    code = "capability_unavailable"

    def __init__(self, capability: str, detail: str) -> None:
        super().__init__(detail)
        self.capability = capability
        self.detail = detail


class BudgetExceeded(RuntimeErrorBase):
    code = "budget_exceeded"


class RunCancelled(RuntimeErrorBase):
    code = "run_cancelled"


class EvidenceInsufficient(RuntimeErrorBase):
    code = "evidence_insufficient"
