"""Production capability tools.

Test doubles belong in ``tests/fakes`` and are injected through the
orchestrator constructor. No automatic substitute registration exists here.
"""

from .capabilities import CapabilityClients, ToolResult

__all__ = ["CapabilityClients", "ToolResult"]
