from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.management import router as management_router
from app.api.router import router as legacy_router
from app.api.runs import router as runs_router
from app.api.websocket import router as websocket_router
from app.auth.router import router as auth_router
from app.core.config import settings
from app.db.database import create_db_and_tables
from app.evolution.continuous import ContinuousEvolutionController
from app.observability.tracing import configure_tracing, safe_span
from app.runtime.orchestrator import RunOrchestrator
from app.runtime.store import RuntimeStore
from app.services.provider_config import ProviderConfigStore
from app.services.state import MemoryStore, SkillStore
from app.tools.capabilities import CapabilityClients


@asynccontextmanager
async def lifespan(app: FastAPI):
    errors = settings.startup_errors()
    if settings.STRICT_STARTUP and settings.ENVIRONMENT != "test" and errors:
        raise RuntimeError("启动前配置检查失败：" + "；".join(errors))
    create_db_and_tables()
    configure_tracing(settings)
    store = RuntimeStore(settings)
    clients = CapabilityClients(settings)
    evolution_controller = ContinuousEvolutionController(settings)
    memory_store = MemoryStore(settings, evolution_controller)
    app.state.runtime_store = store
    app.state.capability_clients = clients
    app.state.memory_store = memory_store
    app.state.skill_store = SkillStore(settings)
    app.state.evolution_controller = evolution_controller
    app.state.provider_config_store = ProviderConfigStore(store, settings)
    app.state.orchestrator = RunOrchestrator(
        store,
        clients,
        settings,
        memory_store=memory_store,
        provider_config_store=app.state.provider_config_store,
        evolution_controller=evolution_controller,
    )
    await app.state.orchestrator.recover_interrupted()
    yield
    tasks = list(app.state.orchestrator._tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await clients.close()


app = FastAPI(
    title="OphAgent-Pro 研究级眼科诊疗增强工作台",
    version=settings.APP_VERSION,
    description="AgentScope 驱动的研究级眼科诊疗增强系统；不替代医生诊断。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_http_request(request, call_next):
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.cookies.get("access_token")
    ):
        origin = request.headers.get("origin")
        if origin:
            request_origin = f"{request.url.scheme}://{request.url.netloc}"
            allowed_origins = {request_origin, *settings.cors_origin_list}
            if origin not in allowed_origins:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "跨站请求已被拒绝"},
                )
    with safe_span(
        "http.request",
        **{
            "http.request.method": request.method,
            "server.address": request.url.hostname or "",
        },
    ) as span:
        response = await call_next(request)
        span.set_attribute("http.response.status_code", response.status_code)
        return response

static_dir = settings.project_root / "app" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(legacy_router, prefix="/api/v1")
app.include_router(runs_router, prefix="/api/v1")
app.include_router(management_router, prefix="/api/v1")
app.include_router(websocket_router, prefix="/ws")
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

frontend_dist = settings.project_root / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="frontend-assets")


@app.get("/", include_in_schema=False)
async def root():
    index = frontend_dist / "index.html"
    if index.is_file():
        return FileResponse(index)
    return RedirectResponse("/docs")


@app.get("/{path:path}", include_in_schema=False)
async def frontend_route(path: str):
    if path.startswith(("api/", "auth/", "ws/", "static/")):
        return RedirectResponse("/docs")
    index = frontend_dist / "index.html"
    if index.is_file():
        return FileResponse(index)
    return RedirectResponse("/docs")
