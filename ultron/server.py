# Copyright (c) ModelScope Contributors. All rights reserved.
import asyncio
import logging
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

embedding_queue = None
_decay_task = None
_logger = logging.getLogger("ultron.server")


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


async def _decay_loop():
    u = server_state.ultron
    assert u is not None
    interval = u.config.decay_interval_hours * 3600
    while True:
        await asyncio.sleep(interval)
        try:
            summary = u.run_tier_rebalance()
            _logger.info("Background tier rebalance completed: %s", summary)
        except Exception:
            _logger.exception("Background tier rebalance failed")
        if u.config.consolidate_enabled:
            try:
                result = u.memory_service.consolidate_memories()
                if result["merges"] > 0:
                    _logger.info("Background consolidation completed: %s", result)
            except Exception:
                _logger.exception("Background consolidation failed")


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
    _decay_task = asyncio.create_task(_decay_loop())
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
