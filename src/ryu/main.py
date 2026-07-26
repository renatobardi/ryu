"""Ryu — app FastAPI (integração de todos os domínios).

Lifespan: init_db → APScheduler (autopilots cron) → runner (fila AgentTask).
Routers montados nos prefixos do CONTRACTS.md; páginas HTML sem prefixo.
WS realtime em /ws/{workspace_id} conectado ao hub.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from ryu.config import settings
from ryu.db import init_db
from ryu.realtime.hub import hub
from ryu.runner import start_runner, stop_runner
from ryu.services.automation import register_autopilot_jobs

from ryu.api import agents as agents_api
from ryu.api import auth as auth_api
from ryu.api import autopilots as autopilots_api
from ryu.api import chat as chat_api
from ryu.api import inbox as inbox_api
from ryu.api import issues as issues_api
from ryu.api import pages as pages_api
from ryu.api import skills as skills_api
from ryu.api import squads as squads_api

log = structlog.get_logger("ryu.main")

_STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    scheduler = AsyncIOScheduler()
    scheduler.start()
    await register_autopilot_jobs(scheduler)
    start_runner()
    log.info("ryu_started", port=settings.port)
    yield
    await stop_runner()
    scheduler.shutdown(wait=False)
    log.info("ryu_stopped")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# ── Static ────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# ── APIs JSON (prefixos do CONTRACTS.md item 8) ───────────────────────
app.include_router(auth_api.router, prefix="/api/auth", tags=["auth"])
app.include_router(issues_api.router, prefix="/api/issues", tags=["issues"])
app.include_router(agents_api.router, prefix="/api/agents", tags=["agents"])
app.include_router(agents_api.tasks_router, prefix="/api/tasks", tags=["tasks"])
app.include_router(chat_api.router, prefix="/api/chat", tags=["chat"])
app.include_router(skills_api.router, prefix="/api/skills", tags=["skills"])
app.include_router(autopilots_api.router, prefix="/api/autopilots", tags=["autopilots"])
app.include_router(squads_api.router, prefix="/api/squads", tags=["squads"])
app.include_router(inbox_api.router, prefix="/api/inbox", tags=["inbox"])
app.include_router(inbox_api.usage_router, prefix="/api/usage", tags=["usage"])

# ── Páginas HTML (rotas específicas antes do catch-all /w/{slug}) ─────
app.include_router(issues_api.pages_router, tags=["pages"])
app.include_router(agents_api.pages_router, tags=["pages"])
app.include_router(chat_api.pages_router, tags=["pages"])
app.include_router(skills_api.pages_router, tags=["pages"])
app.include_router(autopilots_api.pages_router, tags=["pages"])
app.include_router(squads_api.pages_router, tags=["pages"])
app.include_router(inbox_api.pages_router, tags=["pages"])
app.include_router(pages_api.router, tags=["pages"])  # / , /login , /w/{slug} — por último


# ── Realtime WS ───────────────────────────────────────────────────────
@app.websocket("/ws/{workspace_id}")
async def websocket_endpoint(websocket: WebSocket, workspace_id: str):
    await hub.connect(workspace_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive; cliente não precisa enviar nada
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.disconnect(workspace_id, websocket)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "app": settings.app_name}


def run() -> None:
    import uvicorn

    uvicorn.run("ryu.main:app", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    run()
