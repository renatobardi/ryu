"""Serviço de chat — sessões de conversa 1:1 entre usuário e agente.

Exporta:
- CRUD de ChatSession (create/list/get/rename/archive/pin/delete)
- add_user_message(db, session, content): cria ChatMessage(role='user') e
  enfileira AgentTask(kind='chat') com o histórico recente como prompt.
  Recusa sessão arquivada; dispara geração assíncrona de título via LLM
  (best-effort, compare-and-swap) na primeira mensagem.
- pending task discovery: get_pending_task / list_pending_tasks / has_pending_tasks.
- cancelamento integrado: cancel_pending_task + finalize_cancelled_chat_task
  (draft restore quando a resposta ficou vazia — multica 182/183).
- draft restores: list_draft_restores / consume_draft_restore.
- unread: mark_session_read (cursor last_read_at) + unread_since setado quando
  o agente responde (multica 040/151).
- pinned agents (barra de quick-agents): list/pin/unpin (multica 152/153).
- handle_chat_task_done(task): chamada pelo RUNNER quando uma AgentTask com
  kind='chat' termina (completed/failed/cancelled). Persiste a resposta como
  ChatMessage(role='agent') e publica 'chat:message' + 'chat:done' no hub.
  O runner NÃO precisa passar uma sessão de DB — a função abre a própria.
"""
from __future__ import annotations

import asyncio
import re

import structlog
from fastapi import HTTPException
from sqlalchemy import delete, func, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from ryu.db import SessionLocal
from ryu.models import (
    Agent,
    AgentTask,
    ChannelChatLink,
    ChannelInstallation,
    ChatDraftRestore,
    ChatMessage,
    ChatPinnedAgent,
    ChatSession,
    TaskMessage,
    now,
)
from ryu.realtime.hub import hub

log = structlog.get_logger("ryu.chat")

TITLE_MAX_LEN = 60
HISTORY_LIMIT = 20  # mensagens incluídas no prompt enviado ao agente
PENDING_STATUSES = ("queued", "dispatched", "running")

PROMPT_HEADER = (
    "Você é um agente respondendo em uma sessão de chat com um usuário. "
    "Abaixo está o histórico recente da conversa. Responda a última mensagem "
    "do usuário de forma direta e útil.\n\n"
)

_ROLE_LABEL = {"user": "Usuário", "agent": "Agente", "system": "Sistema"}

_TITLE_PREFIX_RE = re.compile(r"^\s*(t[íi]tulo|title)\s*[:\-]\s*", re.IGNORECASE)


def _truncate_title(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= TITLE_MAX_LEN:
        return text or "Nova conversa"
    return text[: TITLE_MAX_LEN - 1].rstrip() + "…"


def sanitize_title(raw: str) -> str:
    """Sanitização do título gerado por LLM (multica sanitizeChatTitle):
    remove aspas, prefixos 'Título:', pontuação final e aplica cap de 60."""
    title = (raw or "").strip().splitlines()[0] if (raw or "").strip() else ""
    title = title.strip().strip("\"'`“”‘’").strip()
    title = _TITLE_PREFIX_RE.sub("", title)
    title = title.strip().strip("\"'`“”‘’").strip()
    title = title.rstrip(".!?…,;:").strip()
    title = " ".join(title.split())
    if len(title) > TITLE_MAX_LEN:
        title = title[: TITLE_MAX_LEN - 1].rstrip() + "…"
    return title


async def _generate_title_async(session_id: str, first_message: str, fallback_title: str) -> None:
    """Geração best-effort do título via LLM. Nunca propaga erro; escrita
    compare-and-swap para não sobrescrever rename manual."""
    try:
        from ryu.services.llm import generate_text

        raw = await generate_text(
            "Gere um título curto (máx 8 palavras) para uma conversa que começa com a "
            f"mensagem abaixo. Responda APENAS o título, sem aspas nem prefixos.\n\n{first_message[:2000]}",
            max_tokens=48,
        )
        title = sanitize_title(raw or "")
        if not title:
            return  # fallback silencioso: fica o título truncado
        workspace_id: str | None = None
        async with SessionLocal() as db:
            # CAS: só aplica se o título ainda é o fallback (ninguém renomeou)
            res = await db.execute(
                sql_update(ChatSession)
                .where(ChatSession.id == session_id, ChatSession.title == fallback_title)
                .values(title=title)
            )
            await db.commit()
            if (res.rowcount or 0) > 0:
                row = await db.get(ChatSession, session_id)
                workspace_id = row.workspace_id if row else None
        if workspace_id:
            await hub.publish(
                workspace_id,
                "chat:session_updated",
                {"session_id": session_id, "title": title},
            )
    except Exception:
        log.warning("chat_title_generation_failed", session_id=session_id)


def session_has_unread(session: ChatSession) -> bool:
    return getattr(session, "unread_since", None) is not None


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
    agent = res.scalars().first()
    if agent is None or getattr(agent, "archived_at", None) is not None:
        raise HTTPException(status_code=404, detail="Agente não encontrado neste workspace")
    # canInvokeAgent (multica): chat também é ponto de disparo
    from ryu.services import agents as agents_svc

    await agents_svc.ensure_can_invoke(db, user_id, agent)
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
    await hub.publish(
        session.workspace_id,
        "chat:session_updated",
        {
            "session_id": session.id,
            "title": session.title,
            "archived": session.archived,
            "pinned": session.pinned,
        },
    )
    return session


async def _cancel_session_tasks(db: AsyncSession, session: ChatSession) -> list[AgentTask]:
    """Cancela tasks pendentes (queued/dispatched/running) da sessão.
    Não commita — o chamador decide. O runner observa cancel_requested."""
    res = await db.execute(
        select(AgentTask).where(
            AgentTask.chat_session_id == session.id,
            AgentTask.status.in_(PENDING_STATUSES),
        )
    )
    tasks = list(res.scalars().all())
    for t in tasks:
        t.status = "cancelled"
        t.cancel_requested = True
        t.finished_at = now()
    return tasks


async def delete_session(db: AsyncSession, session: ChatSession) -> None:
    """Apaga a sessão + mensagens, cancelando a task pendente na mesma tx
    (multica DeleteChatSession, chat.go:558)."""
    workspace_id, session_id = session.workspace_id, session.id
    cancelled = await _cancel_session_tasks(db, session)
    await db.execute(delete(ChatDraftRestore).where(ChatDraftRestore.session_id == session_id))
    res = await db.execute(select(ChatMessage).where(ChatMessage.session_id == session_id))
    for msg in res.scalars().all():
        await db.delete(msg)
    await db.delete(session)
    await db.commit()
    for t in cancelled:
        await hub.publish(workspace_id, "task:cancelled", {"task_id": t.id, "reason": "session_deleted"})
    await hub.publish(workspace_id, "chat:session_deleted", {"session_id": session_id})


# ── Unread / mark-read ────────────────────────────────────────────────
async def mark_session_read(db: AsyncSession, session: ChatSession) -> ChatSession:
    """POST /read: limpa o cursor de não-lido (multica MarkChatSessionRead)."""
    had_unread = session.unread_since is not None
    session.last_read_at = now()
    session.unread_since = None
    await db.commit()
    if had_unread:
        await hub.publish(
            session.workspace_id,
            "chat:session_read",
            {"session_id": session.id, "last_read_at": session.last_read_at},
        )
    return session


# ── Pending task discovery ────────────────────────────────────────────
async def get_pending_task(db: AsyncSession, session_id: str) -> AgentTask | None:
    res = await db.execute(
        select(AgentTask)
        .where(
            AgentTask.chat_session_id == session_id,
            AgentTask.kind == "chat",
            AgentTask.status.in_(PENDING_STATUSES),
        )
        .order_by(AgentTask.created_at.desc())
        .limit(1)
    )
    return res.scalars().first()


def pending_task_out(task: AgentTask | None) -> dict | None:
    if task is None:
        return None
    return {
        "id": task.id,
        "session_id": task.chat_session_id,
        "agent_id": task.agent_id,
        "status": task.status,
        "created_at": task.created_at,
    }


async def list_pending_tasks(
    db: AsyncSession, *, workspace_id: str, user_id: str
) -> list[AgentTask]:
    """Tasks de chat pendentes de TODAS as sessões do usuário no workspace."""
    res = await db.execute(
        select(AgentTask)
        .join(ChatSession, ChatSession.id == AgentTask.chat_session_id)
        .where(
            ChatSession.workspace_id == workspace_id,
            ChatSession.user_id == user_id,
            AgentTask.kind == "chat",
            AgentTask.status.in_(PENDING_STATUSES),
        )
        .order_by(AgentTask.created_at.desc())
    )
    return list(res.scalars().all())


# ── Transcript parcial (streaming da resposta em andamento) ───────────
async def partial_transcript(db: AsyncSession, task_id: str, limit: int = 200) -> dict:
    """TaskMessages da task em execução, para render como mensagem parcial do
    agente (multica EventTaskMessage / ChatWindow em andamento)."""
    res = await db.execute(
        select(TaskMessage)
        .where(TaskMessage.task_id == task_id)
        .order_by(TaskMessage.seq, TaskMessage.created_at)
        .limit(limit)
    )
    texts: list[str] = []
    activity: list[str] = []
    for m in res.scalars().all():
        mtype = m.type or m.role
        if mtype == "assistant" and m.content:
            texts.append(m.content)
        elif mtype == "tool_use":
            activity.append(f"→ {m.tool or 'tool'}")
        elif mtype in ("stdout", "progress") and m.content:
            activity.append(m.content[:200])
    return {"texts": texts, "activity": activity[-5:]}


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
    if session.archived:
        # multica SendChatMessage: 'chat session is archived'
        raise HTTPException(status_code=409, detail="Sessão arquivada é somente leitura")

    # agente precisa continuar invocável (arquivado/permissão revogada → bloqueia)
    res = await db.execute(select(Agent).where(Agent.id == session.agent_id))
    agent = res.scalars().first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agente desta sessão não existe mais")
    from ryu.services import agents as agents_svc

    await agents_svc.ensure_can_invoke(db, session.user_id, agent)

    # título autogerado na primeira mensagem (fallback truncado + LLM async)
    res = await db.execute(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == session.id)
    )
    is_first = (res.scalar() or 0) == 0
    fallback_title: str | None = None
    if is_first and session.title in ("", "Nova conversa"):
        fallback_title = _truncate_title(content)
        session.title = fallback_title

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

    # geração de título via LLM: fire-and-forget, nunca bloqueia o send
    if fallback_title is not None:
        try:
            asyncio.get_running_loop().create_task(
                _generate_title_async(session.id, content, fallback_title)
            )
        except RuntimeError:
            pass  # sem event loop (não deve acontecer em contexto async)

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


# ── Cancelamento integrado + draft restore ────────────────────────────
async def _task_has_output(db: AsyncSession, task: AgentTask) -> bool:
    if (task.result_summary or "").strip():
        return True
    res = await db.execute(
        select(TaskMessage.id)
        .where(TaskMessage.task_id == task.id, TaskMessage.type == "assistant")
        .limit(1)
    )
    return res.first() is not None


async def finalize_cancelled_chat_task(db: AsyncSession, task: AgentTask) -> ChatDraftRestore | None:
    """Finaliza o cancelamento de uma task de chat na sessão (multica
    task_chat_finalize_deferred + chat:cancel_finalized):

    - se nenhuma resposta foi produzida, apaga a ChatMessage do usuário que
      disparou a task e persiste o conteúdo em chat_draft_restore para o
      composer recuperar;
    - publica chat:cancel_finalized + chat:done na sessão.
    """
    if task.kind != "chat" or not task.chat_session_id:
        return None
    res = await db.execute(select(ChatSession).where(ChatSession.id == task.chat_session_id))
    session = res.scalars().first()
    if session is None:
        return None

    restore: ChatDraftRestore | None = None
    if not await _task_has_output(db, task):
        # última mensagem da sessão é a do usuário que disparou a task?
        res = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        last = res.scalars().first()
        if last is not None and last.role == "user":
            existing = await db.get(ChatDraftRestore, last.id)
            if existing is None:
                restore = ChatDraftRestore(
                    id=last.id,
                    session_id=session.id,
                    task_id=task.id,
                    content=last.content,
                )
                db.add(restore)
                await db.delete(last)
            else:
                restore = existing
    session.updated_at = now()
    await db.commit()

    await hub.publish(
        session.workspace_id,
        "chat:cancel_finalized",
        {
            "session_id": session.id,
            "task_id": task.id,
            "restore_id": restore.id if restore else None,
            "content": restore.content if restore else None,
        },
    )
    await hub.publish(
        session.workspace_id,
        "chat:done",
        {"session_id": session.id, "task_id": task.id, "status": "cancelled"},
    )
    return restore


async def cancel_pending_task(
    db: AsyncSession, session: ChatSession
) -> tuple[AgentTask | None, ChatDraftRestore | None]:
    """Botão 'parar' do composer: cancela a task pendente da sessão.

    Marca cancelled + cancel_requested (o runner observa e mata o subprocesso)
    e finaliza na sessão (draft restore quando não houve resposta)."""
    task = await get_pending_task(db, session.id)
    if task is None:
        return None, None
    task.status = "cancelled"
    task.cancel_requested = True
    task.finished_at = now()
    await db.commit()
    await hub.publish(session.workspace_id, "task:cancelled", {"task_id": task.id})
    restore = await finalize_cancelled_chat_task(db, task)
    return task, restore


async def list_draft_restores(db: AsyncSession, session_id: str) -> list[ChatDraftRestore]:
    res = await db.execute(
        select(ChatDraftRestore)
        .where(ChatDraftRestore.session_id == session_id)
        .order_by(ChatDraftRestore.created_at)
    )
    return list(res.scalars().all())


def draft_restore_out(r: ChatDraftRestore) -> dict:
    return {
        "id": r.id,
        "session_id": r.session_id,
        "task_id": r.task_id,
        "content": r.content,
        "created_at": r.created_at,
    }


async def consume_draft_restore(
    db: AsyncSession, session_id: str, restore_id: str
) -> ChatDraftRestore | None:
    """DELETE idempotente: remove e devolve o restore (None se já consumido)."""
    row = await db.get(ChatDraftRestore, restore_id)
    if row is None or row.session_id != session_id:
        return None
    await db.delete(row)
    await db.commit()
    return row


# ── Pinned agents (barra de quick-agents) ─────────────────────────────
async def list_pinned_agents(
    db: AsyncSession, *, workspace_id: str, user_id: str
) -> list[Agent]:
    """Agentes fixados do usuário, na ordem; drop silencioso de arquivados."""
    res = await db.execute(
        select(ChatPinnedAgent, Agent)
        .join(Agent, Agent.id == ChatPinnedAgent.agent_id)
        .where(
            ChatPinnedAgent.workspace_id == workspace_id,
            ChatPinnedAgent.user_id == user_id,
        )
        .order_by(ChatPinnedAgent.position, ChatPinnedAgent.created_at)
    )
    agents: list[Agent] = []
    for _pin, agent in res.all():
        if getattr(agent, "archived_at", None) is not None:
            continue  # filtro de agentes arquivados/inacessíveis
        agents.append(agent)
    return agents


async def pin_agent(
    db: AsyncSession, *, workspace_id: str, user_id: str, agent_id: str
) -> ChatPinnedAgent:
    """Pin idempotente com cap (multica chat_pinned_agent)."""
    from ryu.config import settings

    res = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.workspace_id == workspace_id)
    )
    agent = res.scalars().first()
    if agent is None or getattr(agent, "archived_at", None) is not None:
        raise HTTPException(status_code=404, detail="Agente não encontrado neste workspace")

    res = await db.execute(
        select(ChatPinnedAgent).where(
            ChatPinnedAgent.workspace_id == workspace_id,
            ChatPinnedAgent.user_id == user_id,
        )
    )
    pins = list(res.scalars().all())
    for p in pins:
        if p.agent_id == agent_id:
            return p  # idempotente
    cap = getattr(settings, "chat_pinned_agents_cap", 8)
    if len(pins) >= cap:
        raise HTTPException(status_code=409, detail=f"Máximo de {cap} agentes fixados")
    position = max((p.position for p in pins), default=0.0) + 1.0
    pin = ChatPinnedAgent(
        workspace_id=workspace_id, user_id=user_id, agent_id=agent_id, position=position
    )
    db.add(pin)
    await db.commit()
    return pin


async def unpin_agent(
    db: AsyncSession, *, workspace_id: str, user_id: str, agent_id: str
) -> None:
    await db.execute(
        delete(ChatPinnedAgent).where(
            ChatPinnedAgent.workspace_id == workspace_id,
            ChatPinnedAgent.user_id == user_id,
            ChatPinnedAgent.agent_id == agent_id,
        )
    )
    await db.commit()


# ── Callback do runner ────────────────────────────────────────────────
async def handle_chat_task_done(task: AgentTask) -> ChatMessage | None:
    """Chamada pelo runner ao finalizar uma AgentTask kind='chat'.

    Persiste task.result_summary como ChatMessage(role='agent') — ou o erro
    como role='system' se a task falhou — marca a sessão como não-lida e
    publica eventos no hub. Abre a própria sessão de DB.
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

        if task.status == "cancelled":
            # se o cancelamento já foi finalizado com draft restore, não polui a conversa
            res = await db.execute(
                select(ChatDraftRestore.id).where(ChatDraftRestore.task_id == task.id).limit(1)
            )
            if res.first() is not None:
                workspace_id, session_id = session.workspace_id, session.id
                await hub.publish(
                    workspace_id,
                    "chat:done",
                    {"session_id": session_id, "task_id": task.id, "status": "cancelled"},
                )
                return None
            role = "system"
            content = "Resposta cancelada."
            if task.result_summary:
                content += f" Resposta parcial: {task.result_summary[:1000]}"
        elif task.status == "failed" or (task.error and not task.result_summary):
            role = "system"
            content = f"O agente falhou ao responder: {task.error or 'erro desconhecido'}"
        else:
            role = "agent"
            content = task.result_summary or "(resposta vazia)"

        msg = ChatMessage(session_id=session.id, role=role, content=content)
        db.add(msg)
        session.updated_at = now()
        # unread: resposta do agente chegou; o cliente limpa via POST /read
        if session.unread_since is None:
            session.unread_since = now()
        await db.commit()
        await db.refresh(msg)
        workspace_id = session.workspace_id
        session_id = session.id

        # ponte canal→agente (multica router.go: outbound reply): se esta
        # sessão está vinculada a um canal (Slack/Lark), entrega a resposta
        # real do agente de volta ao thread de origem.
        link_res = await db.execute(
            select(ChannelChatLink).where(ChannelChatLink.chat_session_id == session_id)
        )
        link = link_res.scalars().first()
        if link is not None and role in ("agent", "system"):
            installation = await db.get(ChannelInstallation, link.installation_id)
            if installation is not None and installation.status == "active":
                from ryu.services import integrations as integrations_svc

                try:
                    if link.channel_type == "slack":
                        await integrations_svc.send_slack_message(
                            installation, link.external_channel_id, content,
                            thread_ts=link.external_thread_id or None,
                        )
                    elif link.channel_type == "lark":
                        await integrations_svc.send_lark_message(
                            installation, link.external_channel_id, content
                        )
                except Exception as e:  # nunca falha o chat por causa do canal
                    log.error("channel_outbound_failed", channel_type=link.channel_type, error=str(e))

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
    await hub.publish(
        workspace_id,
        "chat:session_updated",
        {"session_id": session_id, "has_unread": True},
    )
    return msg
