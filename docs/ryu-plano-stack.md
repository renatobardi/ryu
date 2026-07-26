# Ryu — Clone do Multica em Python puro, Docker único

Plano de uso pessoal · Julho 2026

---

## Parte 1 — O que o Multica é (mapa do original)

O Multica é um **issue tracker estilo Linear onde agentes de IA de código são membros da equipe**. Você atribui uma issue a um agente (`claude`, `codex`, `gemini`, etc.); um daemon na sua máquina faz claim da task, cria um workspace isolado, roda o CLI do agente e devolve progresso, comentários e mudanças de status em tempo real.

Arquitetura original (Go + TypeScript):

```
Next.js 16 (:3000) ──proxy──▶ Backend Go/Chi (:8080)
                                   │ REST + WebSocket
                                   ▼
                              PostgreSQL 17 (pgvector) · Redis opcional · S3/disco
                                   ▲
                   WS /api/daemon/ws + claim de tasks
                                   │
                        Daemon local ──spawn──▶ claude / codex / gemini / ...
```

Domínios do produto: workspaces + membros + auth por código de e-mail; issues (board, labels, prioridades, sub-issues, dependências, posição float p/ drag-and-drop, metadata KV); **agentes** com fila de tasks em tabela Postgres; **squads** (agente líder delega); **autopilots** (cron/webhook → cria issue → roteia a agente); **skills** versionadas anexáveis a agentes; **chat** com streaming; inbox/notificações; dashboards de uso (tokens/custo); integrações GitHub/Slack/Lark.

Detalhes de design que valem copiar literalmente:

- **Fila = tabela Postgres** (`agent_task_queue`) com claim via lock — sem RabbitMQ/Celery.
- **Três tipos de token**: `mul_` (usuário/PAT), `mdt_` (daemon), `mat_` (task do agente, escopo estreito, servidor sobrescreve identidade). É o modelo de segurança para agentes autônomos.
- **Assignee polimórfico** (`assignee_type` + `assignee_id`: member | agent).
- **`position` FLOAT** para ordenação drag-and-drop (média entre vizinhos).
- **Prepare-lease** no claim (task não fica presa se o daemon morrer) + recover-orphans.
- Taxonomia de eventos WS (`issue:created`, `task:progress`, `chat:message`, …) já padronizada.
- Sem SMTP configurado, o código de login sai no log — perfeito para self-host pessoal.

---

## Parte 2 — Stack Python de ponta (2026)

### Tooling (o novo padrão)
| Ferramenta | Papel | Por quê |
|---|---|---|
| **uv** | Gestão de pacotes/projeto/Python | Substituiu pip+poetry+pyenv+virtualenv. Escrito em Rust, ordens de magnitude mais rápido. `uv sync` no Dockerfile. |
| **Ruff** | Lint + format | Substituiu black+isort+flake8+pylint num binário só. |
| **ty / pyrefly / mypy** | Type checking | ty (Astral) e pyrefly (Meta) são os checkers Rust de nova geração; mypy segue o baseline. |
| **pytest + pytest-asyncio + testcontainers** | Testes | Padrão absoluto; testcontainers para Postgres real nos testes. |
| **Python 3.13+** | Runtime | JIT e free-threading amadurecendo; asyncio muito mais rápido que na era 3.10. |

### Web/API
| Ferramenta | Papel |
|---|---|
| **FastAPI** | O framework dominante para APIs async — OpenAPI grátis, WebSocket nativo, DI. Escolha principal. |
| **Litestar** | Alternativa séria (mais opinionada, DTOs, performance), vale conhecer. |
| **Pydantic v2** | Validação/serialização (core em Rust). Contratos de toda a API. |
| **uvicorn** (ou granian, servidor Rust em ascensão) | ASGI server. |
| **SQLAlchemy 2.0 async + asyncpg + Alembic** | ORM/queries + migrações. SQLModel se quiser unificar Pydantic+ORM. |
| **HTMX + Jinja2 + Tailwind** (ou frontend React separado) | Para UI num container único, HTMX é a via "tudo em Python". |

### AI/Agentes (o que está em alta)
| Ferramenta | Papel |
|---|---|
| **Pydantic AI** | Framework de agentes type-safe — encaixe natural com FastAPI/Pydantic. Ideal para o chat e o "agente líder" de squads. |
| **LangGraph** | Orquestração de workflows de agentes com estado (grafo) — para fluxos de delegação/briefing. |
| **Claude Agent SDK / OpenAI Agents SDK** | SDKs oficiais para rodar agentes de código programaticamente. |
| **LiteLLM** | Proxy unificado para qualquer provedor LLM (títulos de chat, resumos). |
| **MCP (Model Context Protocol)** | Padrão de integração de ferramentas — o "Composio" de 2026 é falar MCP nativo. |

### Infra do clone
| Ferramenta | Papel |
|---|---|
| **APScheduler 4** | Cron in-process (autopilots, rollups) — substitui robfig/cron. |
| **Typer + Rich + httpx** | CLI `ryu` (equivalente ao cobra). |
| **asyncio.create_subprocess_exec** | Daemon: spawn dos CLIs de agente com streaming de stdout. |
| **structlog** | Logging estruturado. |
| **Postgres 17 (pgvector opcional)** | Única fonte de verdade. Redis dispensável em nó único. |

---

## Parte 3 — Mapeamento componente a componente

| Multica (Go/TS) | Ryu (Python) |
|---|---|
| Chi router + middleware | FastAPI + dependências |
| sqlc + pgx | SQLAlchemy 2.0 async + Alembic |
| gorilla/websocket hub | FastAPI WebSocket + hub in-memory (dict por workspace) |
| robfig/cron | APScheduler no mesmo event loop |
| `agent_task_queue` | Mesma tabela + `SELECT ... FOR UPDATE SKIP LOCKED` |
| Daemon Go | Módulo Python asyncio no MESMO processo (nó único!) — sem WS daemon↔server, chamadas diretas |
| Next.js 16 | HTMX + Jinja2 + Tailwind (SSE/WS para realtime) |
| JWT + cookies + PATs | python-jose/PyJWT + mesmos prefixos `ryu_`/`rdt_`/`rat_` |
| Resend/SMTP | Código de login no log (uso pessoal) |
| S3/MinIO | Disco local (`/data/uploads`) |
| Redis | Omitido (single-node) |
| openai-go (títulos de chat) | LiteLLM ou Pydantic AI |

O ganho estrutural do container único: como daemon e servidor viram o mesmo processo, todo o protocolo daemon↔backend (register/heartbeat/claim/ws) colapsa em chamadas de função — mas vale manter a **task queue em tabela** e a máquina de estados `queued→dispatched→running→completed|failed|cancelled` idênticas, para poder externalizar o daemon depois.

---

## Parte 4 — Arquitetura do Docker único

```
┌────────────── container ryu ───────────────┐
│ supervisord (ou s6-overlay)                │
│ ├─ postgres 17 (localhost:5432)            │
│ └─ uvicorn app.main:app (:8000)            │
│      ├─ FastAPI  → API REST + WS + HTMX UI │
│      ├─ APScheduler → autopilots, rollups  │
│      └─ AgentRunner → spawn claude/codex…  │
│ volumes: /data/pgdata /data/uploads        │
│          /data/workspaces                  │
└────────────────────────────────────────────┘
```

Dockerfile (esqueleto):

```dockerfile
FROM python:3.13-slim
RUN apt-get update && apt-get install -y postgresql-17 supervisor git curl nodejs npm \
    && npm i -g @anthropic-ai/claude-code @openai/codex   # CLIs de agente
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
# entrypoint: init pgdata se vazio → alembic upgrade head → supervisord
CMD ["/app/docker/entrypoint.sh"]
```

Estrutura do projeto:

```
ryu/
├─ pyproject.toml            # uv, ruff, pytest config
├─ src/ryu/
│  ├─ main.py                # FastAPI + lifespan (scheduler, runner)
│  ├─ api/                   # routers: auth, issues, agents, tasks, chat, autopilots, skills
│  ├─ models/                # SQLAlchemy (issue, agent, task, skill, squad, autopilot…)
│  ├─ schemas/               # Pydantic v2
│  ├─ services/              # regras de negócio + máquina de estados de task
│  ├─ realtime/hub.py        # eventos WS (mesma taxonomia do multica)
│  ├─ runner/                # "daemon" embutido: claim, workspace, spawn, streaming, GC
│  ├─ agents/                # adapters: claude, codex, gemini… + Pydantic AI p/ chat/squad
│  ├─ web/                   # templates Jinja2 + HTMX
│  └─ cli.py                 # Typer
├─ alembic/
└─ docker/ (Dockerfile, entrypoint.sh, supervisord.conf)
```

---

## Parte 5 — Ordem de implementação

1. **Fundação** — scaffold uv + FastAPI + Postgres + Alembic; auth (código no log, JWT cookie, PAT `ryu_`); workspace/member.
2. **Tracker** — issues, labels, comentários, board HTMX com position float, activity log, hub WS.
3. **Agentes** — tabela agent + task queue (SKIP LOCKED) + AgentRunner spawnando `claude -p`/`codex exec` em `/data/workspaces/<task>`, streaming de progresso, tokens `rat_`, GC de workspaces.
4. **Chat** — sessões com streaming (Pydantic AI/Claude Agent SDK), títulos via LiteLLM.
5. **Autopilots + Skills** — APScheduler cron + endpoint webhook com signing secret; skills markdown+arquivos injetadas no workspace da task.
6. **Squads + extras** — líder delega via LangGraph/Pydantic AI; inbox, dashboards de uso, integração GitHub (webhook + PAT) por último.

Referências no repo original (clonado para análise): `server/cmd/server/router.go` (~300 rotas), `server/pkg/protocol/events.go`, `server/migrations/001_init.up.sql`, `server/internal/daemon/`, `CLI_AND_DAEMON.md`, `.env.example`.
