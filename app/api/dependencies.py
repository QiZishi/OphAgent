from collections.abc import AsyncIterator

from fastapi import Depends, Request

from app.auth.security import get_current_user
from app.db.models import User
from app.evolution.continuous import ContinuousEvolutionController
from app.runtime.orchestrator import RunOrchestrator
from app.runtime.store import RuntimeStore
from app.services.provider_config import ProviderConfigStore
from app.services.state import MemoryStore, SkillStore
from app.tools.capabilities import CapabilityClients


def get_runtime_store(request: Request) -> RuntimeStore:
    return request.app.state.runtime_store


def get_orchestrator(request: Request) -> RunOrchestrator:
    return request.app.state.orchestrator


async def get_capability_clients(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> AsyncIterator[CapabilityClients]:
    provider_store = request.app.state.provider_config_store
    if not await provider_store.has_overrides(int(current_user.id)):
        yield request.app.state.capability_clients
        return
    clients = CapabilityClients(await provider_store.resolved_settings(int(current_user.id)))
    try:
        yield clients
    finally:
        await clients.close()


def get_memory_store(request: Request) -> MemoryStore:
    return request.app.state.memory_store


def get_skill_store(request: Request) -> SkillStore:
    return request.app.state.skill_store


def get_provider_config_store(request: Request) -> ProviderConfigStore:
    return request.app.state.provider_config_store


def get_evolution_controller(request: Request) -> ContinuousEvolutionController:
    return request.app.state.evolution_controller
