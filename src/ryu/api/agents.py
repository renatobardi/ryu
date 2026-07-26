"""API do domínio AGENTS + TASKS (fila de execução).

- `router`: montar com prefix="/api/agents"
- `tasks_router`: montar com prefix="/api/tasks"
- `pages_router`: página /w/{slug}/agents, montar SEM prefixo
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import get_db
from ryu.models import Agent, AgentTask, TaskMessage, User, Workspace, now
from ryu.realtime.hub import hub
from ryu.services.auth import current_user

router = APIRouter()
tasks_router = APIRouter()
pages_router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

AGENT_STATUSES = ["idle", "working", "blocked", "error", "offline"]


def agent_to_dict(a: Agent) -> dict:
    return {
        "id": a.id,
        "workspace_id": a.workspace_id,
        "name": a.name,
        "handle": a.handle,
        "description": a.description,
        "runtime": a.runtime,
        "runtime_config": a.runtime_config,
        "status": a.status,
        "max_concurrent_tasks": a.max_concurrent_tasks,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def task_to_dict(t: AgentTask) -> dict:
    return {
        "id": t.id,
        "workspace_id": t.workspace_id,
        "agent_id": t.agent_id,
        "issue_id": t.issue_id,
        "chat_session_id": t.chat_session_id,
        "kind": t.kind,
        "status": t.status,
        "prompt": t.prompt,
        "result_summary": t.result_summary,
        "error": t.error,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
        "input_tokens": t.input_tokens,
        "output_tokens": t.output_tokens,
        "cost_usd": t.cost_usd,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


class AgentCreate(BaseModel):
    workspace_id: str
    name: str
    handle: str = ""
    description: str = ""
    runtime: str = "claude"
    runtime_config: dict = {}
    max_concurrent_tasks: int = 1


class AgentUpdate(BaseModel):
    name: str | None = None
    handle: str | None = None
    description: str | None = None
    runtime: str | None = None
    runtime_config: dict | None = None
    status: str | None = None
    max_concurrent_tasks: int | None = None


async def _get_agent(db: AsyncSession, agent_id: str) -> Agent:
    res = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = res.scalars().first()
    if agent is None:
        raise HTTPException(404, "agent não encontrado")
    return agent


# ── Agents CRUD ───────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_agent(payload: AgentCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    handle = (payload.handle or payload.name).strip().lstrip("@").lower().replace(" ", "-")
    agent = Agent(
        workspace_id=payload.workspace_id,
        name=payload.name.strip(),
        handle=handle,
        description=payload.description,
        runtime=payload.runtime,
        runtime_config=payload.runtime_config or {},
        max_concurrent_tasks=payload.max_concurrent_tasks,
    )
    db.add(agent)
    await db.commit()
    await hub.publish(agent.workspace_id, "agent:status", {"agent_id": agent.id, "status": agent.status})
    return agent_to_dict(agent)


@router.get("")
async def list_agents(workspace_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    res = await db.execute(select(Agent).where(Agent.workspace_id == workspace_id).order_by(Agent.name))
    return [agent_to_dict(a) for a in res.scalars()]


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return agent_to_dict(await _get_agent(db, agent_id))


@router.patch("/{agent_id}")
async def update_agent(agent_id: str, payload: AgentUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    agent = await _get_agent(db, agent_id)
    changes = {k: getattr(payload, k) for k in payload.model_fields_set}
    if "status" in changes and changes["status"] not in AGENT_STATUSES:
        raise HTTPException(422, f"status inválido: {changes['status']}")
    for k, v in changes.items():
        setattr(agent, k, v)
    await db.commit()
    if "status" in changes:
        await hub.publish(agent.workspace_id, "agent:status", {"agent_id": agent.id, "status": agent.status})
    return agent_to_dict(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    agent = await _get_agent(db, agent_id)
    await db.delete(agent)
    await db.commit()
    return Response(status_code=204)


# ── Tasks (fila) ──────────────────────────────────────────────────────
@tasks_router.get("")
async def list_tasks(
    workspace_id: str,
    status: str | None = None,
    agent_id: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(AgentTask).where(AgentTask.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(AgentTask.status == status)
    if agent_id:
        stmt = stmt.where(AgentTask.agent_id == agent_id)
    if kind:
        stmt = stmt.where(AgentTask.kind == kind)
    stmt = stmt.order_by(AgentTask.created_at.desc()).limit(min(limit, 200))
    res = await db.execute(stmt)
    return [task_to_dict(t) for t in res.scalars()]


@tasks_router.get("/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    res = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = res.scalars().first()
    if task is None:
        raise HTTPException(404, "task não encontrada")
    return task_to_dict(task)


@tasks_router.get("/{task_id}/messages")
async def task_messages(task_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    res = await db.execute(
        select(TaskMessage).where(TaskMessage.task_id == task_id).order_by(TaskMessage.created_at)
    )
    return [
        {"id": m.id, "role": m.role, "content": m.content,
         "created_at": m.created_at.isoformat() if m.created_at else None}
        for m in res.scalars()
    ]


@tasks_router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    res = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = res.scalars().first()
    if task is None:
        raise HTTPException(404, "task não encontrada")
    if task.status not in ("queued", "dispatched", "running"):
        raise HTTPException(409, f"task não pode ser cancelada no status {task.status}")
    task.status = "cancelled"
    task.finished_at = now()
    await db.commit()
    await hub.publish(task.workspace_id, "task:cancelled", {"task_id": task.id})
    return task_to_dict(task)


# ── Página /w/{slug}/agents ───────────────────────────────────────────
async def _workspace_by_slug(db: AsyncSession, slug: str) -> Workspace:
    res = await db.execute(select(Workspace).where(Workspace.slug == slug))
    ws = res.scalars().first()
    if ws is None:
        raise HTTPException(404, "workspace não encontrado")
    return ws


@pages_router.get("/w/{slug}/agents", response_class=HTMLResponse)
async def agents_page(slug: str, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    ws = await _workspace_by_slug(db, slug)
    res = await db.execute(select(Agent).where(Agent.workspace_id == ws.id).order_by(Agent.name))
    agents = list(res.scalars())
    res = await db.execute(
        select(AgentTask).where(AgentTask.workspace_id == ws.id)
        .order_by(AgentTask.created_at.desc()).limit(20)
    )
    tasks = list(res.scalars())
    agent_names = {a.id: a.name for a in agents}
    return templates.TemplateResponse(
        "agents/index.html",
        {
            "request": request,
            "user": user,
            "workspace": ws,
            "active_nav": "agents",
            "agents": agents,
            "tasks": tasks,
            "agent_names": agent_names,
        },
    )


@pages_router.post("/w/{slug}/agents")
async def agents_page_create(
    slug: str,
    name: str = Form(...),
    handle: str = Form(""),
    description: str = Form(""),
    runtime: str = Form("claude"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ws = await _workspace_by_slug(db, slug)
    h = (handle or name).strip().lstrip("@").lower().replace(" ", "-")
    agent = Agent(workspace_id=ws.id, name=name.strip(), handle=h, description=description, runtime=runtime)
    db.add(agent)
    await db.commit()
    await hub.publish(ws.id, "agent:status", {"agent_id": agent.id, "status": agent.status})
    return RedirectResponse(f"/w/{slug}/agents", status_code=303)
