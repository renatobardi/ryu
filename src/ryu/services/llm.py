"""LLM auxiliar do Ryu (títulos de chat etc.).

Integração externa ativável por env var (RYU_ANTHROPIC_API_KEY ou
RYU_OPENAI_API_KEY). Sem chave configurada, `generate_text` devolve None e
loga em debug — os chamadores fazem fallback silencioso.

Código completo: chamada HTTP direta (httpx) à API Anthropic Messages ou a
qualquer endpoint OpenAI-compatível (RYU_OPENAI_BASE_URL). O modelo vem de
settings.litellm_model (formato litellm 'provider/modelo' aceito).
"""
from __future__ import annotations

import httpx
import structlog

from ryu.config import settings

log = structlog.get_logger("ryu.llm")


def llm_available() -> bool:
    return bool(settings.anthropic_api_key or settings.openai_api_key)


def _model_name() -> str:
    model = settings.litellm_model or ""
    # aceita formato litellm 'anthropic/claude-...' ou 'openai/gpt-...'
    if "/" in model:
        return model.split("/", 1)[1]
    return model or "claude-3-5-haiku-20241022"


async def _anthropic(prompt: str, max_tokens: int, system: str | None) -> str | None:
    body: dict = {
        "model": _model_name(),
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
        )
        r.raise_for_status()
        data = r.json()
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return "".join(parts).strip() or None


async def _openai(prompt: str, max_tokens: int, system: str | None) -> str | None:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        r = await client.post(
            f"{settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": _model_name(), "max_tokens": max_tokens, "messages": messages},
        )
        r.raise_for_status()
        data = r.json()
    try:
        return (data["choices"][0]["message"]["content"] or "").strip() or None
    except (KeyError, IndexError, TypeError):
        return None


async def generate_text(
    prompt: str, *, max_tokens: int = 64, system: str | None = None
) -> str | None:
    """Gera texto curto via LLM. Best-effort: None quando não configurado ou em erro."""
    if not llm_available():
        log.debug("llm_not_configured", hint="set RYU_ANTHROPIC_API_KEY ou RYU_OPENAI_API_KEY")
        return None
    try:
        if settings.anthropic_api_key:
            return await _anthropic(prompt, max_tokens, system)
        return await _openai(prompt, max_tokens, system)
    except Exception as exc:  # noqa: BLE001 — auxiliar nunca derruba o fluxo principal
        log.warning("llm_generate_failed", error=str(exc)[:300])
        return None
