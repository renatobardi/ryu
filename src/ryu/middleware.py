"""Middlewares HTTP do app (registrados por install_middlewares em main.py).

- CSRF (workspace-auth ciclo 1; paridade multica middleware/auth.go): quando a
  auth vem de COOKIE (não Bearer), métodos mutantes em /api/* exigem header
  X-CSRF-Token válido (HMAC vinculado ao JWT do cookie).
- Métricas HTTP (usage-observability ciclo 1): contadores/histograma por
  método+rota templada, desligável por RYU_METRICS_ENABLED=false.
"""
from __future__ import annotations

import contextlib
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ryu.config import settings
from ryu.services import metrics as metrics_svc
from ryu.services.auth import AUTH_COOKIE, validate_csrf_token

CSRF_EXEMPT = (
    "/api/auth/request-code",
    "/api/auth/verify",
    "/api/auth/google",
    "/api/auth/logout",
    "/api/webhooks/",
)

_MUTATING_METHODS = ("POST", "PUT", "PATCH", "DELETE")


async def csrf_middleware(request: Request, call_next):
    if (
        request.method in _MUTATING_METHODS
        and request.url.path.startswith("/api/")
        and not request.url.path.startswith(CSRF_EXEMPT)
        and not request.headers.get("Authorization", "").lower().startswith("bearer ")
        and request.cookies.get(AUTH_COOKIE)
    ):
        header = request.headers.get("X-CSRF-Token", "")
        if not validate_csrf_token(header, request.cookies[AUTH_COOKIE]):
            return JSONResponse(status_code=403, content={"detail": "invalid CSRF token"})
    return await call_next(request)


async def metrics_middleware(request: Request, call_next):
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
    with contextlib.suppress(Exception):
        metrics_svc.observe_http(request.method, route_path, response.status_code, duration)
    return response


def install_middlewares(app: FastAPI) -> None:
    """Registra os middlewares na ordem em que devem rodar."""
    app.middleware("http")(csrf_middleware)
    app.middleware("http")(metrics_middleware)
