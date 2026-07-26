# Ryu — Contratos (LEIA ANTES DE ESCREVER QUALQUER CÓDIGO)

Regras para todos os agentes construtores:

1. **Não altere** `models.py`, `db.py`, `config.py`, `realtime/hub.py`, `pyproject.toml`. Se faltar algo, anote no seu relatório final — não edite.
2. Cada domínio escreve APENAS nos seus arquivos designados (router em `src/ryu/api/<dominio>.py`, service em `src/ryu/services/<dominio>.py`, templates em `src/ryu/web/templates/<dominio>/`).
3. Todos os routers expõem `router = APIRouter()`. A integração no `main.py` é feita depois — NÃO editem `main.py`.
4. DB: use `Depends(get_db)` de `ryu.db`. Python 3.11, SQLAlchemy 2.0 async, `select()` style.
5. Eventos realtime: `from ryu.realtime.hub import hub; await hub.publish(workspace_id, "issue:created", {...})`. Use a taxonomia comentada no hub.py.
6. Auth: use `from ryu.services.auth import current_user` (dependency FastAPI que retorna User) — o agente de auth é quem a implementa; os demais apenas importam.
7. UI: HTMX + Jinja2 + Tailwind (CDN), dark theme estilo Linear. Template base em `web/templates/base.html` (feito pelo agente de UI); os demais estendem `{% extends "base.html" %}`.
8. Prefixos de rota: `/api/auth`, `/api/issues`, `/api/agents`, `/api/tasks`, `/api/chat`, `/api/skills`, `/api/autopilots`, `/api/inbox`. Páginas HTML em `/w/{slug}/...`.
9. Status de issue: backlog|todo|in_progress|in_review|done|blocked|cancelled. Task: queued|dispatched|running|completed|failed|cancelled.
10. Sem dependências novas fora do pyproject. Sem type-checker frescuras: código que roda > código bonito.
