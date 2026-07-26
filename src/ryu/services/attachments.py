"""Serviço de ATTACHMENTS (uploads em issues/comentários).

Storage plugável por env var (paridade com ATTACHMENT_*/S3 do multica):
- local (default): grava em settings.uploads_dir/<id>/<filename>, servido em /uploads/*.
- s3: ativado quando RYU_S3_BUCKET + credenciais estão configurados (ou
  RYU_ATTACHMENT_STORAGE=s3). Implementa AWS SigV4 direto com httpx —
  PUT/DELETE de objeto e presigned GET — compatível com S3/R2/MinIO.
  Sem credenciais configuradas o modo s3 degrada com erro claro no log.
"""
from __future__ import annotations

import hashlib
import hmac
import mimetypes
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import httpx
import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.config import settings
from ryu.models import Attachment, Comment, Issue

log = structlog.get_logger("ryu.attachments")


class AttachmentError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def attachment_to_dict(a: Attachment) -> dict:
    return {
        "id": a.id,
        "workspace_id": a.workspace_id,
        "issue_id": a.issue_id,
        "comment_id": a.comment_id,
        "uploader_type": a.uploader_type,
        "uploader_id": a.uploader_id,
        "filename": a.filename,
        "url": a.url,
        "download_url": f"/api/attachments/{a.id}/download",
        "content_url": f"/api/attachments/{a.id}/content",
        "content_type": a.content_type,
        "size_bytes": a.size_bytes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ── Storage backends ──────────────────────────────────────────────────
def storage_mode() -> str:
    mode = (settings.attachment_storage or "auto").lower()
    if mode == "s3":
        return "s3"
    if mode == "local":
        return "local"
    # auto
    if settings.s3_bucket and settings.s3_access_key_id and settings.s3_secret_access_key:
        return "s3"
    return "local"


def _s3_host() -> str:
    if settings.s3_endpoint:
        return urllib.parse.urlparse(settings.s3_endpoint).netloc
    return f"{settings.s3_bucket}.s3.{settings.s3_region}.amazonaws.com"


def _s3_base_url() -> str:
    if settings.s3_endpoint:
        return f"{settings.s3_endpoint.rstrip('/')}/{settings.s3_bucket}"
    return f"https://{_s3_host()}"


def _s3_object_path(key: str) -> str:
    """Caminho do objeto na URL (path-style p/ endpoint custom, virtual-host na AWS)."""
    if settings.s3_endpoint:
        return f"/{settings.s3_bucket}/{key}"
    return f"/{key}"


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _sigv4_headers(method: str, key: str, payload: bytes, content_type: str = "") -> tuple[str, dict]:
    """Assina requisição S3 (header auth). Retorna (url, headers)."""
    host = _s3_host()
    path = _s3_object_path(key)
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(payload).hexdigest()

    headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    if content_type:
        headers["content-type"] = content_type
    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
    canonical_request = "\n".join(
        [method, urllib.parse.quote(path), "", canonical_headers, signed_headers, payload_hash]
    )
    scope = f"{datestamp}/{settings.s3_region}/s3/aws4_request"
    string_to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()]
    )
    k = _sign(f"AWS4{settings.s3_secret_access_key}".encode(), datestamp)
    k = _sign(k, settings.s3_region)
    k = _sign(k, "s3")
    k = _sign(k, "aws4_request")
    signature = hmac.new(k, string_to_sign.encode(), hashlib.sha256).hexdigest()

    auth = (
        f"AWS4-HMAC-SHA256 Credential={settings.s3_access_key_id}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    out = {k2: v for k2, v in headers.items() if k2 != "host"}
    out["Authorization"] = auth
    scheme = "https"
    if settings.s3_endpoint:
        scheme = urllib.parse.urlparse(settings.s3_endpoint).scheme or "https"
    return f"{scheme}://{host}{path}", out


def presign_get(key: str, ttl: int | None = None) -> str:
    """Presigned GET (query auth SigV4) para download direto do bucket."""
    host = _s3_host()
    path = _s3_object_path(key)
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    scope = f"{datestamp}/{settings.s3_region}/s3/aws4_request"
    params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{settings.s3_access_key_id}/{scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(ttl or settings.attachment_download_url_ttl),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_qs = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in sorted(params.items())
    )
    canonical_request = "\n".join(
        ["GET", urllib.parse.quote(path), canonical_qs, f"host:{host}\n", "host", "UNSIGNED-PAYLOAD"]
    )
    string_to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()]
    )
    k = _sign(f"AWS4{settings.s3_secret_access_key}".encode(), datestamp)
    k = _sign(k, settings.s3_region)
    k = _sign(k, "s3")
    k = _sign(k, "aws4_request")
    signature = hmac.new(k, string_to_sign.encode(), hashlib.sha256).hexdigest()
    scheme = "https"
    if settings.s3_endpoint:
        scheme = urllib.parse.urlparse(settings.s3_endpoint).scheme or "https"
    return f"{scheme}://{host}{path}?{canonical_qs}&X-Amz-Signature={signature}"


def _s3_key(att_id: str, filename: str) -> str:
    return f"attachments/{att_id}/{filename}"


async def _s3_put(key: str, payload: bytes, content_type: str) -> str:
    if not (settings.s3_bucket and settings.s3_access_key_id and settings.s3_secret_access_key):
        raise AttachmentError("storage S3 não configurado (RYU_S3_BUCKET/credenciais)", 500)
    url, headers = _sigv4_headers("PUT", key, payload, content_type)
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.put(url, content=payload, headers=headers)
    if r.status_code >= 300:
        log.error("s3_put_failed", status=r.status_code, body=r.text[:500])
        raise AttachmentError("falha no upload para S3", 502)
    if settings.s3_public_base_url:
        return f"{settings.s3_public_base_url.rstrip('/')}/{key}"
    return f"{_s3_base_url()}/{key}" if not settings.s3_endpoint else f"{_s3_base_url().rsplit('/', 1)[0]}/{settings.s3_bucket}/{key}"


async def _s3_delete(key: str) -> None:
    try:
        url, headers = _sigv4_headers("DELETE", key, b"")
        async with httpx.AsyncClient(timeout=30) as client:
            await client.delete(url, headers=headers)
    except Exception as e:  # GC é best-effort
        log.warning("s3_delete_failed", key=key, error=str(e))


def _local_path(att_id: str, filename: str) -> Path:
    return Path(settings.uploads_dir) / att_id / filename


def sanitize_filename(name: str) -> str:
    name = (name or "file").replace("\\", "/").split("/")[-1].strip()
    name = name.replace("\x00", "")
    return name or "file"


def guess_content_type(filename: str, declared: str | None) -> str:
    if declared and declared not in ("application/octet-stream", ""):
        return declared
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


# ── CRUD ──────────────────────────────────────────────────────────────
async def create_attachment(
    db: AsyncSession,
    workspace_id: str,
    uploader_type: str,
    uploader_id: str,
    *,
    filename: str,
    content: bytes,
    content_type: str | None = None,
    issue_id: str | None = None,
    comment_id: str | None = None,
) -> Attachment:
    if uploader_type not in ("member", "agent"):
        raise AttachmentError(f"uploader_type inválido: {uploader_type}")
    if len(content) == 0:
        raise AttachmentError("arquivo vazio")
    if len(content) > settings.attachment_max_size_bytes:
        raise AttachmentError(
            f"arquivo excede o limite de {settings.attachment_max_size_bytes} bytes", 413
        )
    filename = sanitize_filename(filename)
    ctype = guess_content_type(filename, content_type)

    if issue_id:
        issue = await db.get(Issue, issue_id)
        if issue is None or issue.workspace_id != workspace_id:
            raise AttachmentError("issue não encontrada neste workspace", 404)
    if comment_id:
        comment = await db.get(Comment, comment_id)
        if comment is None:
            raise AttachmentError("comentário não encontrado", 404)
        if issue_id and comment.issue_id != issue_id:
            raise AttachmentError("comentário não pertence à issue")
        if not issue_id:
            issue = await db.get(Issue, comment.issue_id)
            if issue is None or issue.workspace_id != workspace_id:
                raise AttachmentError("comentário de outro workspace", 404)
            issue_id = comment.issue_id

    from ryu.models import uid

    att = Attachment(
        id=uid(),  # id explícito: usado no path do storage antes do flush
        workspace_id=workspace_id,
        issue_id=issue_id,
        comment_id=comment_id,
        uploader_type=uploader_type,
        uploader_id=uploader_id,
        filename=filename,
        url="",
        content_type=ctype,
        size_bytes=len(content),
    )

    if storage_mode() == "s3":
        att.url = await _s3_put(_s3_key(att.id, filename), content, ctype)
    else:
        path = _local_path(att.id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        att.url = f"/uploads/{att.id}/{urllib.parse.quote(filename)}"

    db.add(att)
    await db.commit()
    return att


async def get_attachment(db: AsyncSession, attachment_id: str) -> Attachment:
    att = await db.get(Attachment, attachment_id)
    if att is None:
        raise AttachmentError("attachment não encontrado", 404)
    return att


async def list_issue_attachments(db: AsyncSession, issue_id: str) -> list[Attachment]:
    rows = await db.execute(
        select(Attachment).where(Attachment.issue_id == issue_id).order_by(Attachment.created_at)
    )
    return list(rows.scalars())


def resolve_download(att: Attachment) -> tuple[str, str]:
    """Retorna ("file", caminho_local) ou ("redirect", url) p/ servir o conteúdo."""
    if att.url.startswith("/uploads/"):
        return "file", str(_local_path(att.id, att.filename))
    # objeto em S3/R2/MinIO — presigned GET quando temos credenciais
    if settings.s3_access_key_id and settings.s3_secret_access_key and settings.s3_bucket:
        return "redirect", presign_get(_s3_key(att.id, att.filename))
    return "redirect", att.url


async def delete_stored(att: Attachment) -> None:
    """Remove o binário do storage (best-effort, chamado após o commit)."""
    if att.url.startswith("/uploads/"):
        try:
            p = _local_path(att.id, att.filename)
            if p.exists():
                p.unlink()
            if p.parent.exists() and not any(p.parent.iterdir()):
                p.parent.rmdir()
        except Exception as e:
            log.warning("local_delete_failed", attachment_id=att.id, error=str(e))
    else:
        await _s3_delete(_s3_key(att.id, att.filename))


async def delete_attachment(db: AsyncSession, attachment_id: str) -> None:
    att = await get_attachment(db, attachment_id)
    await db.delete(att)
    await db.commit()
    await delete_stored(att)


async def collect_for_issue(db: AsyncSession, issue_id: str) -> list[Attachment]:
    """Attachments da issue + dos seus comentários (p/ GC no delete da issue)."""
    rows = await db.execute(select(Attachment).where(Attachment.issue_id == issue_id))
    return list(rows.scalars())


async def collect_for_comment(db: AsyncSession, comment_id: str) -> list[Attachment]:
    rows = await db.execute(select(Attachment).where(Attachment.comment_id == comment_id))
    return list(rows.scalars())


async def delete_rows_for_issue(db: AsyncSession, issue_id: str) -> None:
    await db.execute(delete(Attachment).where(Attachment.issue_id == issue_id))


async def delete_rows_for_comment(db: AsyncSession, comment_id: str) -> None:
    await db.execute(delete(Attachment).where(Attachment.comment_id == comment_id))
