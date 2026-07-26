# Ryu — Contratos (LEIA ANTES DE ESCREVER QUALQUER CÓDIGO)

Regras para todos os agentes construtores:

1. **Não altere** `models.py`, `db.py`, `config.py`, `realtime/hub.py`, `pyproject.toml`. Se faltar algo, anote no seu relatório final — não edite.
2. Cada domínio escreve APENAS nos seus arquivos designados (router em `src/ryu/api/<dominio>.py`, service em `src/ryu/services/<dominio>.py`, templates em `src/ryu/web/templates/<dominio>/`). Exceção: componentes Jinja compartilhados (Button, StatusPill, Sidebar etc.) são cross-cutting e moram em `src/ryu/web/templates/_components/{core,data,app}/`.
3. Todos os routers expõem `router = APIRouter()`. A integração no `main.py` é feita depois — NÃO editem `main.py`.
4. DB: use `Depends(get_db)` de `ryu.db`. Python 3.11, SQLAlchemy 2.0 async, `select()` style.
5. Eventos realtime: `from ryu.realtime.hub import hub; await hub.publish(workspace_id, "issue:created", {...})`. Use a taxonomia comentada no hub.py.
6. Auth: use `from ryu.services.auth import current_user` (dependency FastAPI que retorna User) — o agente de auth é quem a implementa; os demais apenas importam.
7. UI: HTMX + Jinja2 + Tailwind (CDN), design system Ryu (`docs/Ryu Design System/`) — tema **claro e escuro** via atributo `data-theme` no `<html>` (cookie `ryu_theme` por browser, default claro), accent único cyan-600 (`#0891b2`), ícones Lucide (CDN) com 🤖/👤 como marcador semântico. Cores/tema só via classes Tailwind semânticas (`bg-surface-*`, `text-text-*`, `bg-status-*` etc., ver `src/ryu/web/static/app.css`) — nunca `style` inline nem `gray-*`/`indigo-*` cru. Template base em `web/templates/base.html` (feito pelo agente de UI); os demais estendem `{% extends "base.html" %}`.
8. Prefixos de rota: `/api/auth`, `/api/issues`, `/api/agents`, `/api/tasks`, `/api/chat`, `/api/skills`, `/api/autopilots`, `/api/inbox`. Páginas HTML em `/w/{slug}/...`.
9. Status de issue: backlog|todo|in_progress|in_review|done|blocked|cancelled. Task: queued|dispatched|running|completed|failed|cancelled.
10. Sem dependências novas fora do pyproject. Sem type-checker frescuras: código que roda > código bonito.
