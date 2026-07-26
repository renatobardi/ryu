"""Serviço de INGRESS e ENTREGA de webhooks de autopilot.

- Normalização do corpo recebido num envelope {event, eventPayload, request}.
- Verificação de assinatura HMAC, dedupe e filtros de evento do trigger.
- Persistência das WebhookDelivery + replay de uma delivery armazenada.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone as _timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.models import (
    Autopilot,
    AutopilotRun,
    AutopilotTrigger,
    WebhookDelivery,
    now,
)
from ryu.services.automation import (
    AutomationError,
    _iso,
    get_webhook_trigger_by_token,
    run_autopilot,
)


# ── serializers ───────────────────────────────────────────────────────
def delivery_to_dict(d: WebhookDelivery, *, include_body: bool = False) -> dict:
    out = {
        "id": d.id,
        "workspace_id": d.workspace_id,
        "autopilot_id": d.autopilot_id,
        "trigger_id": d.trigger_id,
        "provider": d.provider,
        "event": d.event,
        "dedupe_key": d.dedupe_key,
        "dedupe_source": d.dedupe_source,
        "signature_status": d.signature_status,
        "status": d.status,
        "attempt_count": d.attempt_count,
        "selected_headers": d.selected_headers or {},
        "content_type": d.content_type,
        "response_status": d.response_status,
        "response_body": d.response_body,
        "autopilot_run_id": d.autopilot_run_id,
        "replayed_from_delivery_id": d.replayed_from_delivery_id,
        "error": d.error,
        "received_at": _iso(d.received_at),
        "last_attempt_at": _iso(d.last_attempt_at),
        "created_at": _iso(d.created_at),
    }
    if include_body:
        out["raw_body"] = d.raw_body
    return out


# ═══════════════ WEBHOOK INGRESS + DELIVERIES (multica 093) ═══════════
SIG_NOT_REQUIRED = "not_required"
SIG_VALID = "valid"
SIG_INVALID = "invalid"
SIG_MISSING = "missing"

_KNOWN_EVENT_PROVIDERS = ("github", "gitlab")


def _strip_bom(b: bytes) -> bytes:
    return b[3:] if b[:3] == b"\xef\xbb\xbf" else b


def normalize_webhook_payload(body: bytes, headers: dict[str, str]) -> dict:
    """Normaliza o corpo num envelope {event, eventPayload, request} (multica
    normalizeWebhookPayload). Levanta AutomationError(400) p/ JSON inválido."""
    body = _strip_bom(body)
    if not body.strip():
        raise AutomationError("empty body")
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError) as e:
        raise AutomationError(f"invalid json: {e}")
    if not isinstance(parsed, (dict, list)):
        raise AutomationError("body must be a JSON object or array")
    content_type = (headers.get("content-type") or "").split(";")[0].strip()
    env: dict[str, Any] = {
        "request": {
            "receivedAt": datetime.now(_timezone.utc).isoformat(),
            "contentType": content_type,
        }
    }
    if isinstance(parsed, dict) and isinstance(parsed.get("event"), str) and parsed["event"]:
        env["event"] = parsed["event"]
        env["eventPayload"] = parsed.get("eventPayload", parsed)
        return env
    env["event"] = _infer_event(headers, parsed)
    env["eventPayload"] = parsed
    return env


def _infer_event(headers: dict[str, str], body: Any) -> str:
    gh = headers.get("x-github-event", "")
    if gh:
        if isinstance(body, dict) and isinstance(body.get("action"), str) and body["action"]:
            return f"github.{gh}.{body['action']}"
        return f"github.{gh}"
    gl = headers.get("x-gitlab-event", "")
    if gl:
        return f"gitlab.{gl}"
    xe = headers.get("x-event-type", "")
    if xe:
        return xe
    if isinstance(body, dict):
        for key in ("event", "type", "action"):
            v = body.get(key)
            if isinstance(v, str) and v:
                return v
    return "webhook.received"


def extract_dedupe_key(provider: str, headers: dict[str, str]) -> tuple[str | None, str | None]:
    ghd = (headers.get("x-github-delivery") or "").strip()
    if ghd and provider == "github":
        return ghd, "x-github-delivery"
    idem = (headers.get("idempotency-key") or "").strip()
    if idem:
        return idem, "idempotency-key"
    if ghd:
        return ghd, "x-github-delivery"
    return None, None


def verify_webhook_signature(secret: str | None, headers: dict[str, str], body: bytes) -> str:
    """HMAC-SHA256 estilo GitHub: X-Hub-Signature-256: sha256=<hex>."""
    if not secret:
        return SIG_NOT_REQUIRED
    sig = headers.get("x-hub-signature-256", "")
    if not sig:
        return SIG_MISSING
    if not sig.startswith("sha256="):
        return SIG_INVALID
    want = sig[len("sha256="):]
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return SIG_VALID if hmac.compare_digest(mac, want) else SIG_INVALID


def selected_headers(headers: dict[str, str]) -> dict:
    """Subset de headers p/ debugging — nunca tokens/assinaturas em claro."""
    out: dict[str, Any] = {}
    for name in ("user-agent", "x-github-event", "x-github-delivery",
                 "x-gitlab-event", "x-event-type", "idempotency-key"):
        if headers.get(name):
            out[name] = headers[name]
    if headers.get("x-hub-signature-256"):
        out["x-hub-signature-256-present"] = True
    return out


def _split_webhook_event(event: str) -> tuple[str, str, str]:
    parts = (event or "").split(".")
    if parts and parts[0] in _KNOWN_EVENT_PROVIDERS:
        if len(parts) >= 3:
            return parts[0], parts[1], ".".join(parts[2:])
        if len(parts) == 2:
            return parts[0], parts[1], ""
        return parts[0], "", ""
    if len(parts) >= 2:
        return "", parts[0], ".".join(parts[1:])
    return "", event, ""


def event_allowed_by_filters(event_filters: list | None, envelope: dict) -> bool:
    """Filtros de evento do trigger (multica webhookEventAllowedByTriggerScope)."""
    if not event_filters:
        return True
    _, name, action = _split_webhook_event(envelope.get("event", ""))
    candidates = {action} if action else set()
    payload = envelope.get("eventPayload")
    if isinstance(payload, dict) and isinstance(payload.get("action"), str):
        candidates.add(payload["action"])
    for f in event_filters:
        if not isinstance(f, dict) or f.get("event") != name:
            continue
        allowed = f.get("actions") or []
        if not allowed:
            return True
        if any(a in allowed for a in candidates):
            return True
        # não retorna False aqui: outros filtros com o mesmo event ainda contam
    return False


async def list_deliveries(
    db: AsyncSession, autopilot_id: str, limit: int = 50, status: str | None = None
) -> list[WebhookDelivery]:
    stmt = (
        select(WebhookDelivery)
        .where(WebhookDelivery.autopilot_id == autopilot_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(WebhookDelivery.status == status)
    rows = await db.execute(stmt)
    return list(rows.scalars())


async def get_delivery(db: AsyncSession, autopilot_id: str, delivery_id: str) -> WebhookDelivery:
    d = await db.get(WebhookDelivery, delivery_id)
    if d is None or d.autopilot_id != autopilot_id:
        raise AutomationError("delivery não encontrada", 404)
    return d


async def _finalize_delivery(
    db: AsyncSession,
    delivery: WebhookDelivery,
    status: str,
    response_status: int,
    response_body: dict,
    error: str = "",
) -> None:
    delivery.status = status
    delivery.response_status = response_status
    delivery.response_body = json.dumps(response_body, ensure_ascii=False)[:4000]
    delivery.error = error
    delivery.last_attempt_at = now()
    await db.commit()


async def webhook_ingress(
    db: AsyncSession, token: str, *, body: bytes, headers: dict[str, str]
) -> tuple[int, dict]:
    """Fluxo persist-first do ingress público (multica HandleAutopilotWebhook).

    Retorna (status_code, response_body). Regras:
    413 corpo acima do cap; 404 token; 400 JSON inválido (sem persistência);
    duplicata → bump attempt_count; assinatura inválida/ausente → rejected 401;
    trigger desabilitado / paused / archived / event filtrado → ignored 200;
    senão dispatch → dispatched 200.
    """
    from ryu.config import settings

    headers = {k.lower(): v for k, v in headers.items()}
    if len(body) > settings.webhook_body_max_bytes:
        return 413, {"error": "payload too large"}
    pair = await get_webhook_trigger_by_token(db, token)
    if pair is None:
        return 404, {"error": "webhook not found"}
    ap, trig = pair
    try:
        envelope = normalize_webhook_payload(body, headers)
    except AutomationError as e:
        return 400, {"error": e.message}

    provider = trig.provider or "generic"
    dedupe_key, dedupe_source = extract_dedupe_key(provider, headers)
    sig_status = verify_webhook_signature(trig.signing_secret, headers, body)

    # dedupe: linha existente não-rejeitada/failed com a mesma chave → bump
    if dedupe_key:
        rows = await db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.trigger_id == trig.id,
                WebhookDelivery.dedupe_key == dedupe_key,
                WebhookDelivery.status.notin_(("rejected", "failed")),
            )
        )
        existing = rows.scalars().first()
        if existing is not None:
            existing.attempt_count = (existing.attempt_count or 1) + 1
            existing.last_attempt_at = now()
            await db.commit()
            resp = {"status": "duplicate", "delivery_id": existing.id}
            if existing.autopilot_run_id:
                resp["run_id"] = existing.autopilot_run_id
            return 200, resp

    delivery = WebhookDelivery(
        workspace_id=ap.workspace_id,
        autopilot_id=ap.id,
        trigger_id=trig.id,
        provider=provider,
        event=envelope.get("event", "webhook.received"),
        dedupe_key=dedupe_key,
        dedupe_source=dedupe_source,
        signature_status=sig_status,
        content_type=envelope["request"].get("contentType") or None,
        raw_body=body.decode("utf-8", errors="replace")[: settings.webhook_body_max_bytes],
        selected_headers=selected_headers(headers),
    )
    db.add(delivery)
    await db.commit()

    if sig_status in (SIG_INVALID, SIG_MISSING):
        reason = "invalid_signature" if sig_status == SIG_INVALID else "missing_signature"
        resp = {"status": "rejected", "delivery_id": delivery.id, "reason": reason}
        await _finalize_delivery(db, delivery, "rejected", 401, resp, reason)
        return 401, resp

    def _ignored(reason: str) -> dict:
        return {"status": "ignored", "delivery_id": delivery.id, "reason": reason}

    if not trig.enabled:
        resp = _ignored("trigger_disabled")
        await _finalize_delivery(db, delivery, "ignored", 200, resp, "trigger_disabled")
        return 200, resp
    ap_status = getattr(ap, "status", "active") or "active"
    if ap_status == "archived":
        resp = _ignored("autopilot_archived")
        await _finalize_delivery(db, delivery, "ignored", 200, resp, "autopilot_archived")
        return 200, resp
    if ap_status != "active" or not ap.enabled:
        resp = _ignored("autopilot_paused")
        await _finalize_delivery(db, delivery, "ignored", 200, resp, "autopilot_paused")
        return 200, resp
    if not event_allowed_by_filters(trig.event_filters, envelope):
        resp = _ignored("event_filtered")
        resp["event"] = envelope.get("event")
        await _finalize_delivery(db, delivery, "ignored", 200, resp, "event_filtered")
        return 200, resp

    try:
        run = await run_autopilot(db, ap, source="webhook", trigger=trig, payload=envelope)
    except Exception as e:  # noqa: BLE001
        resp = {"status": "failed", "delivery_id": delivery.id, "error": str(e)[:500]}
        await _finalize_delivery(db, delivery, "failed", 500, resp, str(e)[:2000])
        return 500, resp
    trig.last_fired_at = now()
    delivery.autopilot_run_id = run.id
    resp = {
        "status": "accepted" if run.status != "skipped" else "skipped",
        "delivery_id": delivery.id,
        "run_id": run.id,
        "autopilot_id": ap.id,
        "trigger_id": trig.id,
    }
    if run.status == "skipped":
        resp["reason"] = run.failure_reason
    await _finalize_delivery(db, delivery, "dispatched", 200, resp)
    return 200, resp


async def replay_delivery(
    db: AsyncSession, ap: Autopilot, delivery_id: str
) -> tuple[WebhookDelivery, AutopilotRun | None]:
    """Recria a delivery a partir do corpo armazenado e redispara (multica
    ReplayAutopilotDelivery). A nova linha aponta replayed_from_delivery_id."""
    original = await get_delivery(db, ap.id, delivery_id)
    if not (original.raw_body or "").strip():
        raise AutomationError("delivery sem corpo armazenado — nada a redisparar", 409)
    trig = await db.get(AutopilotTrigger, original.trigger_id)
    if trig is None:
        raise AutomationError("trigger da delivery não existe mais", 409)
    ap_status = getattr(ap, "status", "active") or "active"
    if ap_status == "archived":
        raise AutomationError("autopilot arquivado não dispara", 409)
    body = original.raw_body.encode("utf-8")
    headers = {"content-type": original.content_type or "application/json"}
    try:
        envelope = normalize_webhook_payload(body, headers)
    except AutomationError:
        # corpo antigo pode ter sido um envelope já normalizado — reusa
        envelope = {"event": original.event, "eventPayload": None, "request": {}}
    replay = WebhookDelivery(
        workspace_id=ap.workspace_id,
        autopilot_id=ap.id,
        trigger_id=trig.id,
        provider=original.provider,
        event=original.event,
        signature_status=SIG_NOT_REQUIRED,  # replay é autenticado pela sessão
        content_type=original.content_type,
        raw_body=original.raw_body,
        selected_headers=original.selected_headers or {},
        replayed_from_delivery_id=original.id,
    )
    db.add(replay)
    await db.commit()
    if ap_status != "active" or not ap.enabled:
        resp = {"status": "ignored", "delivery_id": replay.id, "reason": "autopilot_paused"}
        await _finalize_delivery(db, replay, "ignored", 200, resp, "autopilot_paused")
        return replay, None
    try:
        run = await run_autopilot(db, ap, source="webhook", trigger=trig, payload=envelope)
    except Exception as e:  # noqa: BLE001
        resp = {"status": "failed", "delivery_id": replay.id, "error": str(e)[:500]}
        await _finalize_delivery(db, replay, "failed", 500, resp, str(e)[:2000])
        return replay, None
    replay.autopilot_run_id = run.id
    resp = {"status": "accepted", "delivery_id": replay.id, "run_id": run.id}
    await _finalize_delivery(db, replay, "dispatched", 200, resp)
    return replay, run
