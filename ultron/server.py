# Copyright (c) ModelScope Contributors. All rights reserved.
import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from ultron import Ultron
from ultron import server_state
from ultron.api.routers import auth as auth_router
from ultron.api.routers import dashboard as dashboard_router
from ultron.api.routers import harness as harness_router
from ultron.api.routers import memory as memory_router
from ultron.api.routers import skills as skills_router
from ultron.api.routers import system as system_router
from ultron.core.logging import setup_logging, set_trace_id, log_event
from ultron.services.auth import AuthService
from ultron.services.harness.soul_presets import SoulPresetService
from ultron.services.harness.showcase import ShowcaseService
from ultron.services.skill.skill_cluster import KnowledgeClusterService
from ultron.services.skill.skill_evolution import SkillEvolutionEngine
from ultron.services.background import run_decay_loop
from ultron.services.training.sft_trainer import SFTTrainerService

embedding_queue = None
_decay_task = None

setup_logging(
    log_dir=os.path.join(os.path.expanduser("~/.ultron"), "logs"),
    level=os.environ.get("ULTRON_LOG_LEVEL", "INFO"),
)

server_state.ultron = Ultron()
server_state.auth_service = AuthService(
    secret=server_state.ultron.config.resolve_jwt_secret(),
    expire_hours=server_state.ultron.config.jwt_expire_hours,
)
server_state.soul_preset_service = SoulPresetService()
server_state.soul_preset_service.load()
server_state.showcase_service = ShowcaseService()
server_state.showcase_service.load()

# Initialize evolution services
_u = server_state.ultron
server_state.cluster_service = KnowledgeClusterService(
    _u.db, _u.embedding, _u.config,
)
server_state.evolution_engine = SkillEvolutionEngine(
    database=_u.db,
    storage=_u.storage,
    embedding_service=_u.embedding,
    cluster_service=server_state.cluster_service,
    config=_u.config,
    llm_orchestrator=_u.llm_orchestrator,
    catalog=_u.catalog,
)

server_state.trajectory_service = _u.trajectory_service
server_state.sft_trainer = SFTTrainerService(
    db=_u.db,
    sft_exporter=_u.trajectory_service.sft_exporter,
    config=_u.config,
)


@asynccontextmanager
async def lifespan(app):
    global embedding_queue, _decay_task
    u = server_state.ultron
    assert u is not None
    if u.config.async_embedding:
        from ultron.core.async_queue import EmbeddingQueue

        embedding_queue = EmbeddingQueue(
            u.embedding,
            max_size=u.config.embedding_queue_size,
            workers=u.config.embedding_queue_workers,
        )
        await embedding_queue.start()
    _decay_task = asyncio.create_task(run_decay_loop())
    yield
    _decay_task.cancel()
    if embedding_queue:
        await embedding_queue.shutdown()


app = FastAPI(
    title="Ultron API",
    description="Collective Intelligence",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestTracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tid = set_trace_id()
        method = request.method
        path = request.url.path
        start = time.time()

        log_event(f"→ {method} {path}", method=method, path=path)

        try:
            response = await call_next(request)
            duration_ms = round((time.time() - start) * 1000, 1)
            log_event(
                f"← {response.status_code} {method} {path}",
                method=method,
                path=path,
                status=response.status_code,
                duration_ms=duration_ms,
            )
            response.headers["X-Trace-Id"] = tid
            return response
        except Exception as e:
            duration_ms = round((time.time() - start) * 1000, 1)
            log_event(
                f"← ERROR {method} {path}: {e}",
                level="error",
                method=method,
                path=path,
                duration_ms=duration_ms,
            )
            raise


app.add_middleware(RequestTracingMiddleware)

dashboard_router.mount_dashboard_assets(app)

app.include_router(system_router.router)
app.include_router(memory_router.router)
app.include_router(skills_router.router)
app.include_router(auth_router.router)
app.include_router(harness_router.router)
app.include_router(dashboard_router.router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=9999,
        log_config=None,
    )
