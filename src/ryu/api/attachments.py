"""API de ATTACHMENTS/uploads (paridade multica file.go).

- `upload_router` (prefix /api): POST /upload-file (multipart) + GET/DELETE /attachments/*.
- `uploads_router` (sem prefix): GET /uploads/{...} — serve storage local.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.config import settings
from ryu.db import get_db
from ryu.models import User
from ryu.services import attachments as svc
from ryu.services.auth import current_user

upload_router = APIRouter()
uploads_router = APIRouter()


def _err(e: svc.AttachmentError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.message)


def _actor(user: User) -> tuple[str, str]:
    if user.id.startswith("agent:"):
        return "agent", user.id.split(":", 1)[1]
    return "member", user.id


@upload_router.post("/upload-file", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    workspace_id: str = Form(...),
    issue_id: str | None = Form(None),
    comment_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    content = await file.read()
    utype, uid_ = _actor(user)
    try:
        att = await svc.create_attachment(
            db,
            workspace_id,
            utype,
            uid_,
            filename=file.filename or "file",
            content=content,
            content_type=file.content_type,
            issue_id=issue_id or None,
            comment_id=comment_id or None,
        )
    except svc.AttachmentError as e:
        raise _err(e)
    return svc.attachment_to_dict(att)


@upload_router.get("/attachments/{attachment_id}")
async def get_attachment(
    attachment_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        att = await svc.get_attachment(db, attachment_id)
    except svc.AttachmentError as e:
        raise _err(e)
    return svc.attachment_to_dict(att)


@upload_router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        att = await svc.get_attachment(db, attachment_id)
    except svc.AttachmentError as e:
        raise _err(e)
    kind, target = svc.resolve_download(att)
    if kind == "redirect":
        return RedirectResponse(target, status_code=307)
    if not Path(target).exists():
        raise HTTPException(404, "arquivo não encontrado no storage")
    return FileResponse(
        target,
        media_type=att.content_type,
        filename=att.filename,  # Content-Disposition: attachment
    )


@upload_router.get("/attachments/{attachment_id}/content")
async def attachment_content(
    attachment_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        att = await svc.get_attachment(db, attachment_id)
    except svc.AttachmentError as e:
        raise _err(e)
    kind, target = svc.resolve_download(att)
    if kind == "redirect":
        return RedirectResponse(target, status_code=307)
    if not Path(target).exists():
        raise HTTPException(404, "arquivo não encontrado no storage")
    return FileResponse(
        target,
        media_type=att.content_type,
        headers={"Content-Disposition": f'inline; filename="{att.filename}"'},
    )


@upload_router.delete("/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        await svc.delete_attachment(db, attachment_id)
    except svc.AttachmentError as e:
        raise _err(e)
    return Response(status_code=204)


# ── Serve local (/uploads/*) ──────────────────────────────────────────
@uploads_router.get("/uploads/{file_path:path}")
async def serve_upload(file_path: str):
    root = Path(settings.uploads_dir).resolve()
    target = (root / file_path).resolve()
    if not target.is_relative_to(root):  # path traversal
        raise HTTPException(404, "não encontrado")
    if not target.is_file():
        raise HTTPException(404, "não encontrado")
    return FileResponse(target)
