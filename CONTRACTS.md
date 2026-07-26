# Ryu — Contratos (LEIA ANTES DE ESCREVER QUALQUER CÓDIGO)

Regras para todos os agentes construtores:

1. **Não altere** `models.py`, `db.py`, `config.py`, `realtime/hub.py`, `pyproject.toml`. Se faltar algo, anote no seu relatório final — não edite.
2. Cada domínio escreve APENAS nos seus arquivos designados (router em `src/ryu/api/<dominio>.py`, service em `src/ryu/services/<dominio>.py`, templates em `src/ryu/web/templates/<dominio>/`).
3. Todos os routers expõem `router = APIRouter()`. A integração no `main.py` é feita depois — NÃO editem `main.py`.
4. DB: use `Depends(get_db)` de `ryu.db`. Python 3.11, SQLAlchemy 2.0 async, `select()` style.
5. Eventos realtime: `from ryu.realtime.hub import hub; await hub.publish(workspace_id, "issue:created", {...})`. Use a taxonomia comentada no hub.py.
6. Auth: use `from ryu.services.auth import current_user` (dependency FastAPI que retorna User) — o agente de auth é quem a implementa; os demais apenas importam. Acesso a workspace: `from ryu.services.workspaces import require_access` (papel do user, 403 se não-membro, `'agent'` para tokens rat_/rdt_) e `require_role` para owner/admin — não reimplemente a query em `Member`.
7. UI: HTMX + Jinja2 + Tailwind (CDN), dark theme estilo Linear. Template base em `web/templates/base.html` (feito pelo agente de UI); os demais estendem `{% extends "base.html" %}`.
8. Prefixos de rota: `/api/auth`, `/api/issues`, `/api/agents`, `/api/tasks`, `/api/chat`, `/api/skills`, `/api/autopilots`, `/api/inbox`, `/api/workspaces`, `/api/invitations`, `/api/notification-preferences`, `/api/squads`, `/api/usage`, `/api/projects`, `/api/runtime-profiles`, `/api/search`, `/api/properties`, `/api/pins`, `/api/daemon`, `/api/runtimes`, `/api/integrations`, `/api/dashboard`. Páginas HTML em `/w/{slug}/...`; exceções pré-workspace: `/login`, `/cli-login`, `/invite/{id}`. Ingress sem prefixo: `/api/webhooks/*`, `/uploads/*`.
9. Status de issue: backlog|todo|in_progress|in_review|done|blocked|cancelled. Task: queued|dispatched|running|completed|failed|cancelled.
10. Sem dependências novas fora do pyproject. Sem type-checker frescuras: código que roda > código bonito.

## Registro de exceções à regra 1

O ciclo 1 de paridade precisou editar arquivos travados; fica registrado aqui em vez de só no relatório do agente:

- `models.py`, `config.py`: colunas e settings novos dos 8 domínios (sem eles nenhum domínio roda).
- `db.py`: `apply_light_migrations` (ALTER TABLEs idempotentes para DBs já criados). Não há versionamento de schema — erro que não seja "coluna já existe" é logado como `light_migration_failed`.
- `main.py`: montagem dos routers e `install_middlewares(app)`. Middleware novo vai em `src/ryu/middleware.py`, não em `main.py`.
- `realtime/hub.py`: apenas o comentário da taxonomia de eventos.
