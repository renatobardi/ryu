"""Ryu — app FastAPI (integração de todos os domínios).

Lifespan: init_db → APScheduler (autopilots cron) → runner (fila AgentTask).
Routers montados nos prefixos do CONTRACTS.md; páginas HTML sem prefixo.
WS realtime em /ws/{workspace_id} conectado ao hub.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from ryu.config import settings
from ryu.db import engine, init_db
from ryu.realtime.hub import hub
from ryu.runner import start_runner, stop_runner
from ryu.services import metrics as metrics_svc
from ryu.services.automation import register_autopilot_jobs

from ryu.api import agents as agents_api
from ryu.api import attachments as attachments_api
from ryu.api import auth as auth_api
from ryu.api import dashboard as dashboard_api
from ryu.api import notification_preferences as notification_preferences_api
from ryu.api import workspaces as workspaces_api
from ryu.api import autopilots as autopilots_api
from ryu.api import chat as chat_api
from ryu.api import daemon as daemon_api
from ryu.api import inbox as inbox_api
from ryu.api import integrations as integrations_api
from ryu.api import issues as issues_api
from ryu.api import pages as pages_api
from ryu.api import pins as pins_api
from ryu.api import projects as projects_api
from ryu.api import properties as properties_api
from ryu.api import runtime_profiles as runtime_profiles_api
from ryu.api import skills as skills_api
from ryu.api import squads as squads_api
from ryu.api import workspace_extra as workspace_extra_api

log = structlog.get_logger("ryu.main")

_STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"


async def _rollup_job() -> None:
    from ryu.db import SessionLocal
    from ryu.services.rollup import run_rollup

    try:
        async with SessionLocal() as db:
            result = await run_rollup(db)
            if result.get("rows_processed"):
                log.info("usage_rollup_tick", **result)
    except Exception:
        log.exception("usage_rollup_failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    scheduler = AsyncIOScheduler()
    scheduler.start()
    await register_autopilot_jobs(scheduler)
    scheduler.add_job(
        _rollup_job, "interval",
        seconds=max(5, settings.usage_rollup_interval_seconds),
        id="usage_rollup", replace_existing=True,
    )
    start_runner()
    log.info("ryu_started", port=settings.port)
    yield
    await stop_runner()
    scheduler.shutdown(wait=False)
    log.info("ryu_stopped")


app = FastAPI(title=settings.app_name, lifespan=lifespan)


# ── CSRF (workspace-auth ciclo 1; paridade multica middleware/auth.go) ─
# Quando a auth vem de COOKIE (não Bearer), métodos mutantes em /api/*
# exigem header X-CSRF-Token válido (HMAC vinculado ao JWT do cookie).
_CSRF_EXEMPT = (
    "/api/auth/request-code",
    "/api/auth/verify",
    "/api/auth/google",
    "/api/auth/logout",
    "/api/webhooks/",
)


@app.middleware("http")
async def csrf_middleware(request, call_next):
    from fastapi.responses import JSONResponse

    from ryu.services.auth import AUTH_COOKIE, validate_csrf_token

    if (
        request.method in ("POST", "PUT", "PATCH", "DELETE")
        and request.url.path.startswith("/api/")
        and not request.url.path.startswith(_CSRF_EXEMPT)
        and not request.headers.get("Authorization", "").lower().startswith("bearer ")
        and request.cookies.get(AUTH_COOKIE)
    ):
        header = request.headers.get("X-CSRF-Token", "")
        if not validate_csrf_token(header, request.cookies[AUTH_COOKIE]):
            return JSONResponse(status_code=403, content={"detail": "invalid CSRF token"})
    return await call_next(request)


# ── Métricas HTTP (usage-observability ciclo 1) ────────────────────────
@app.middleware("http")
async def metrics_middleware(request, call_next):
    if not settings.metrics_enabled or request.url.path == "/metrics":
        return await call_next(request)
    metrics_svc.http_in_flight_inc()
    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        metrics_svc.http_in_flight_dec()
    duration = time.perf_counter() - started
    route = request.scope.get("route")
    route_path = getattr(route, "path", None) or request.url.path
    with __import__("contextlib").suppress(Exception):
        metrics_svc.observe_http(request.method, route_path, response.status_code, duration)
    return response

# ── Static ────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# ── APIs JSON (prefixos do CONTRACTS.md item 8) ───────────────────────
app.include_router(auth_api.router, prefix="/api/auth", tags=["auth"])
app.include_router(workspaces_api.router, prefix="/api/workspaces", tags=["workspaces"])
app.include_router(workspaces_api.invitations_router, prefix="/api/invitations", tags=["invitations"])
app.include_router(
    notification_preferences_api.router,
    prefix="/api/notification-preferences",
    tags=["notification-preferences"],
)
app.include_router(issues_api.router, prefix="/api/issues", tags=["issues"])
app.include_router(agents_api.router, prefix="/api/agents", tags=["agents"])
app.include_router(agents_api.tasks_router, prefix="/api/tasks", tags=["tasks"])
app.include_router(chat_api.router, prefix="/api/chat", tags=["chat"])
app.include_router(skills_api.router, prefix="/api/skills", tags=["skills"])
app.include_router(autopilots_api.router, prefix="/api/autopilots", tags=["autopilots"])
app.include_router(squads_api.router, prefix="/api/squads", tags=["squads"])
app.include_router(inbox_api.router, prefix="/api/inbox", tags=["inbox"])
app.include_router(inbox_api.usage_router, prefix="/api/usage", tags=["usage"])
app.include_router(projects_api.router, prefix="/api/projects", tags=["projects"])
app.include_router(runtime_profiles_api.router, prefix="/api/runtime-profiles", tags=["runtime-profiles"])
app.include_router(workspace_extra_api.search_router, prefix="/api/search", tags=["search"])
app.include_router(properties_api.router, prefix="/api/properties", tags=["properties"])
app.include_router(pins_api.router, prefix="/api/pins", tags=["pins"])
app.include_router(attachments_api.upload_router, prefix="/api", tags=["attachments"])
app.include_router(attachments_api.uploads_router, tags=["attachments"])  # /uploads/*
# daemon-cli ciclo 1: API de daemon externo + runtimes + handoff do CLI
app.include_router(daemon_api.router, prefix="/api/daemon", tags=["daemon"])
app.include_router(daemon_api.runtimes_router, prefix="/api/runtimes", tags=["runtimes"])
app.include_router(daemon_api.cli_router, prefix="/api", tags=["cli"])
# integrations ciclo 1: GitHub App, VCS self-hosted, Slack/Lark, webhooks públicos
app.include_router(integrations_api.router, prefix="/api/integrations", tags=["integrations"])
app.include_router(integrations_api.webhooks_router, tags=["webhooks"])
# usage-observability ciclo 1: dashboards de tokens/custo/runtime + atividade
app.include_router(dashboard_api.router, prefix="/api/dashboard", tags=["dashboard"])

# ── Páginas HTML (rotas específicas antes do catch-all /w/{slug}) ─────
app.include_router(issues_api.pages_router, tags=["pages"])
app.include_router(pins_api.pages_router, tags=["pages"])
app.include_router(agents_api.pages_router, tags=["pages"])
app.include_router(chat_api.pages_router, tags=["pages"])
app.include_router(skills_api.pages_router, tags=["pages"])
app.include_router(autopilots_api.pages_router, tags=["pages"])
app.include_router(squads_api.pages_router, tags=["pages"])
app.include_router(inbox_api.pages_router, tags=["pages"])
app.include_router(projects_api.pages_router, tags=["pages"])
app.include_router(workspace_extra_api.pages_router, tags=["pages"])
app.include_router(workspaces_api.pages_router, tags=["pages"])  # /w/{slug}/members, /invite/{id}
app.include_router(daemon_api.pages_router, tags=["pages"])  # /cli-login
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
    """Liveness — sempre 200 se o processo está de pé (não toca o DB)."""
    return {"ok": True, "app": settings.app_name}


_readyz_cache: dict = {"ts": 0.0, "body": None, "status": 200}


@app.get("/readyz")
async def readyz():
    """Readiness real: SELECT no DB + checagem de schema, com cache curto
    (settings.readiness_cache_seconds) para não martelar o banco a cada probe."""
    from sqlalchemy import text

    now = time.monotonic()
    if _readyz_cache["body"] is not None and (now - _readyz_cache["ts"]) < settings.readiness_cache_seconds:
        return JSONResponse(status_code=_readyz_cache["status"], content=_readyz_cache["body"])

    body: dict
    status = 200
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            tables = (
                await conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
            ).scalars().all() if "sqlite" in str(engine.url) else []
        body = {"ok": True, "db": "ok", "schema_tables": len(tables) if tables else None}
    except Exception as exc:  # noqa: BLE001
        status = 503
        body = {"ok": False, "db": "error", "error": str(exc)[:300]}
        log.warning("readyz_failed", error=str(exc)[:300])

    _readyz_cache.update(ts=now, body=body, status=status)
    return JSONResponse(status_code=status, content=body)


@app.get("/metrics")
async def metrics_endpoint():
    """Prometheus text format, gerado manualmente (sem dependência nova).
    Desativável por RYU_METRICS_ENABLED=false (→ 404)."""
    if not settings.metrics_enabled:
        return JSONResponse(status_code=404, content={"detail": "metrics disabled"})
    body = await metrics_svc.render(version="0.1.0", app_name=settings.app_name)
    return PlainTextResponse(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/api/config")
async def public_config():
    """Config pública consumida pelos templates (feature flags server-evaluated)."""
    from ryu.featureflags import flags

    return {"app": settings.app_name, "flags": flags.evaluate_frontend_public_flags()}


def run() -> None:
    import uvicorn

    uvicorn.run("ryu.main:app", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    run()
