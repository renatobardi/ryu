"""API de PINNED ITEMS (montar com prefix /api/pins) + fragmento HTML da sidebar."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import User
from ryu.services import pins as svc
from ryu.services.auth import current_user, current_workspace

router = APIRouter()
pages_router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _err(e: svc.PinError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.message)


class PinCreate(BaseModel):
    workspace_id: str
    item_type: str  # issue|project
    item_id: str


class PinReorder(BaseModel):
    workspace_id: str
    items: list[dict]  # [{item_type, item_id}] na nova ordem


@router.get("")
async def list_pins(
    workspace_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    return await svc.list_pins(db, workspace_id, user.id)


@router.post("", status_code=201)
async def create_pin(
    payload: PinCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        pin = await svc.create_pin(db, payload.workspace_id, user.id, payload.item_type, payload.item_id)
    except svc.PinError as e:
        raise _err(e)
    return svc.pin_to_dict(pin)


@router.put("/reorder")
async def reorder_pins(
    payload: PinReorder, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    try:
        return await svc.reorder_pins(db, payload.workspace_id, user.id, payload.items)
    except svc.PinError as e:
        raise _err(e)


@router.delete("/{item_type}/{item_id}", status_code=204)
async def delete_pin(
    item_type: str,
    item_id: str,
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        await svc.delete_pin(db, workspace_id, user.id, item_type, item_id)
    except svc.PinError as e:
        raise _err(e)
    return Response(status_code=204)


# ── Fragmento da sidebar (HTMX, carregado via hx-get) ─────────────────
@pages_router.get("/w/{slug}/pins", response_class=HTMLResponse)
async def pins_fragment(
    slug: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    ws = await current_workspace(slug, db, user)
    pins = await svc.list_pins(db, ws.id, user.id)
    return templates.TemplateResponse(
        "pins/_sidebar.html", {"request": request, "workspace": ws, "pins": pins}
    )
