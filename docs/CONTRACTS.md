# Ryu — Contratos (LEIA ANTES DE ESCREVER QUALQUER CÓDIGO)

Regras para todos os agentes construtores:

1. **Não altere** `models.py`, `db.py`, `config.py`, `realtime/hub.py`, `pyproject.toml`. Se faltar algo, anote no seu relatório final — não edite.
2. Cada domínio escreve APENAS nos seus arquivos designados (router em `src/ryu/api/<dominio>.py`, service em `src/ryu/services/<dominio>.py`, templates em `src/ryu/web/templates/<dominio>/`). Exceção: componentes Jinja compartilhados (Button, StatusPill, Sidebar etc.) são cross-cutting e moram em `src/ryu/web/templates/_components/{core,data,app}/`.
3. Todos os routers expõem `router = APIRouter()`. A integração no `main.py` é feita depois — NÃO editem `main.py`.
4. DB: use `Depends(get_db)` de `ryu.db`. Python 3.11, SQLAlchemy 2.0 async, `select()` style.
5. Eventos realtime: `from ryu.realtime.hub import hub; await hub.publish(workspace_id, "issue:created", {...})`. Use a taxonomia comentada no hub.py.
6. Auth: use `from ryu.services.auth import current_user` (dependency FastAPI que retorna User) — o agente de auth é quem a implementa; os demais apenas importam.
7. UI: HTMX + Jinja2 + Tailwind (CDN). Template base em `web/templates/base.html`; os demais estendem `{% extends "base.html" %}`. Nunca `style` inline.
   **Hoje** (migração do design system aplicada, #27): tema claro+escuro por `data-theme` no `<html>`, decidido no servidor a partir do cookie `ryu_theme` — o botão que grava o cookie mora no Profile. Cor só por classe semântica (`surface-*`, `text-*`, `border-*`, `accent`, `success-fg`/`danger-fg`, `status-*`), accent ciano, ícones Lucide. A paleta crua do Tailwind (`zinc-*`, `violet-*`, `text-red-*` etc.) é proibida, e a trava é `LEGACY_VOCABULARY` em `tests/conftest.py`. O mapa token → variável CSS está em `docs/tailwind-config-mapping.md`.
8. Prefixos de rota: `/api/auth`, `/api/issues`, `/api/agents`, `/api/tasks`, `/api/chat`, `/api/skills`, `/api/autopilots`, `/api/inbox`. Páginas HTML em `/w/{slug}/...`.
9. Status de issue: backlog|todo|in_progress|in_review|done|blocked|cancelled. Task: queued|dispatched|running|completed|failed|cancelled.
10. Sem dependências novas fora do pyproject. Sem type-checker frescuras: código que roda > código bonito.
