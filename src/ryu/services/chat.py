"""Serviço de chat — sessões de conversa 1:1 entre usuário e agente.

Exporta:
- CRUD de ChatSession (create/list/get/rename/archive/pin/delete)
- add_user_message(db, session, content): cria ChatMessage(role='user') e
  enfileira AgentTask(kind='chat') com o histórico recente como prompt.
- handle_chat_task_done(task): chamada pelo RUNNER quando uma AgentTask com
  kind='chat' termina (completed ou failed). Persiste a resposta como
  ChatMessage(role='agent') e publica 'chat:message' + 'chat:done' no hub.
  O runner NÃO precisa passar uma sessão de DB — a função abre a própria.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import SessionLocal
from ryu.models import Agent, AgentTask, ChatMessage, ChatSession, now
from ryu.realtime.hub import hub

TITLE_MAX_LEN = 60
HISTORY_LIMIT = 20  # mensagens incluídas no prompt enviado ao agente

PROMPT_HEADER = (
    "Você é um agente respondendo em uma sessão de chat com um usuário. "
    "Abaixo está o histórico recente da conversa. Responda a última mensagem "
    "do usuário de forma direta e útil.\n\n"
)

_ROLE_LABEL = {"user": "Usuário", "agent": "Agente", "system": "Sistema"}


def _truncate_title(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= TITLE_MAX_LEN:
        return text or "Nova conversa"
    return text[: TITLE_MAX_LEN - 1].rstrip() + "…"


# ── CRUD de sessões ───────────────────────────────────────────────────
async def create_session(
    db: AsyncSession,
    *,
    workspace_id: str,
    user_id: str,
    agent_id: str,
    title: str = "Nova conversa",
) -> ChatSession:
    res = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.workspace_id == workspace_id)
    )
    if res.scalars().first() is None:
        raise HTTPException(status_code=404, detail="Agente não encontrado neste workspace")
    session = ChatSession(
        workspace_id=workspace_id,
        user_id=user_id,
        agent_id=agent_id,
        title=title or "Nova conversa",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(
    db: AsyncSession,
    *,
    workspace_id: str,
    user_id: str,
    include_archived: bool = False,
) -> list[ChatSession]:
    stmt = select(ChatSession).where(
        ChatSession.workspace_id == workspace_id,
        ChatSession.user_id == user_id,
    )
    if not include_archived:
        stmt = stmt.where(ChatSession.archived.is_(False))
    stmt = stmt.order_by(ChatSession.pinned.desc(), ChatSession.updated_at.desc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_session(db: AsyncSession, session_id: str, user_id: str) -> ChatSession:
    res = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = res.scalars().first()
    if session is None:
        raise HTTPException(status_code=404, detail="Sessão de chat não encontrada")
    # agentes autenticados via token (id 'agent:...') podem ler; usuários só as suas
    if not user_id.startswith("agent:") and session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Sem acesso a esta sessão")
    return session


async def update_session(
    db: AsyncSession,
    session: ChatSession,
    *,
    title: str | None = None,
    archived: bool | None = None,
    pinned: bool | None = None,
) -> ChatSession:
    if title is not None:
        session.title = _truncate_title(title)
    if archived is not None:
        session.archived = archived
    if pinned is not None:
        session.pinned = pinned
    await db.commit()
    await db.refresh(session)
    return session


async def delete_session(db: AsyncSession, session: ChatSession) -> None:
    res = await db.execute(select(ChatMessage).where(ChatMessage.session_id == session.id))
    for msg in res.scalars().all():
        await db.delete(msg)
    await db.delete(session)
    await db.commit()


# ── Mensagens ─────────────────────────────────────────────────────────
async def list_messages(db: AsyncSession, session_id: str) -> list[ChatMessage]:
    res = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    return list(res.scalars().all())


async def _format_prompt(db: AsyncSession, session_id: str) -> str:
    res = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(HISTORY_LIMIT)
    )
    recent = list(res.scalars().all())[::-1]  # cronológico
    lines = [f"{_ROLE_LABEL.get(m.role, m.role)}: {m.content}" for m in recent]
    return PROMPT_HEADER + "\n".join(lines)


async def add_user_message(
    db: AsyncSession, session: ChatSession, content: str
) -> tuple[ChatMessage, AgentTask]:
    """Cria a mensagem do usuário e enfileira uma AgentTask kind='chat'."""
    content = content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Mensagem vazia")

    # título autogerado na primeira mensagem (sem LLM por ora)
    res = await db.execute(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == session.id)
    )
    is_first = (res.scalar() or 0) == 0
    if is_first and session.title in ("", "Nova conversa"):
        session.title = _truncate_title(content)

    msg = ChatMessage(session_id=session.id, role="user", content=content)
    db.add(msg)
    session.updated_at = now()  # sobe a sessão no topo da lista
    await db.flush()

    prompt = await _format_prompt(db, session.id)
    task = AgentTask(
        workspace_id=session.workspace_id,
        agent_id=session.agent_id,
        chat_session_id=session.id,
        kind="chat",
        status="queued",
        prompt=prompt,
    )
    db.add(task)
    await db.commit()
    await db.refresh(msg)
    await db.refresh(task)

    await hub.publish(
        session.workspace_id,
        "chat:message",
        {
            "session_id": session.id,
            "message_id": msg.id,
            "role": "user",
            "content": msg.content,
            "created_at": msg.created_at,
        },
    )
    await hub.publish(
        session.workspace_id,
        "task:queued",
        {"task_id": task.id, "kind": "chat", "chat_session_id": session.id},
    )
    return msg, task


# ── Callback do runner ────────────────────────────────────────────────
async def handle_chat_task_done(task: AgentTask) -> ChatMessage | None:
    """Chamada pelo runner ao finalizar uma AgentTask kind='chat'.

    Persiste task.result_summary como ChatMessage(role='agent') — ou o erro
    como role='system' se a task falhou — e publica eventos no hub.
    Abre a própria sessão de DB (o objeto task pode estar detached).
    """
    if task.kind != "chat" or not task.chat_session_id:
        return None

    async with SessionLocal() as db:
        res = await db.execute(
            select(ChatSession).where(ChatSession.id == task.chat_session_id)
        )
        session = res.scalars().first()
        if session is None:
            return None

        if task.status == "failed" or (task.error and not task.result_summary):
            role = "system"
            content = f"O agente falhou ao responder: {task.error or 'erro desconhecido'}"
        else:
            role = "agent"
            content = task.result_summary or "(resposta vazia)"

        msg = ChatMessage(session_id=session.id, role=role, content=content)
        db.add(msg)
        session.updated_at = now()
        await db.commit()
        await db.refresh(msg)
        workspace_id = session.workspace_id
        session_id = session.id

    await hub.publish(
        workspace_id,
        "chat:message",
        {
            "session_id": session_id,
            "message_id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at,
        },
    )
    await hub.publish(
        workspace_id,
        "chat:done",
        {"session_id": session_id, "task_id": task.id, "status": task.status},
    )
    return msg
