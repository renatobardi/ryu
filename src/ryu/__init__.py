"""Pacote Ryu.

Compat: Starlette >= 1.x removeu a assinatura antiga de
Jinja2Templates.TemplateResponse(name, context). Os routers de domínio
usam o estilo antigo (request dentro do context), então instalamos um
shim aqui — este módulo é importado antes de qualquer ryu.api.*.
"""
from __future__ import annotations

from typing import Any

from starlette.templating import Jinja2Templates

_orig_template_response = Jinja2Templates.TemplateResponse


def _compat_template_response(self, *args: Any, **kwargs: Any):
    # Estilo novo: (request, name, context, ...)
    if args and not isinstance(args[0], str):
        return _orig_template_response(self, *args, **kwargs)
    # Estilo antigo: (name, context, ...) com request no context
    name = args[0] if args else kwargs.pop("name")
    context = args[1] if len(args) > 1 else kwargs.pop("context", {}) or {}
    request = context.get("request") or kwargs.pop("request", None)
    if request is None:
        raise ValueError("TemplateResponse estilo antigo requer 'request' no context")
    rest = args[2:]
    return _orig_template_response(self, request, name, context, *rest, **kwargs)


if not getattr(Jinja2Templates.TemplateResponse, "_ryu_compat", False):
    _compat_template_response._ryu_compat = True  # type: ignore[attr-defined]
    Jinja2Templates.TemplateResponse = _compat_template_response  # type: ignore[method-assign]
