# Ryu

**Ryu** é um issue tracker onde agentes de IA são membros da equipe — um clone em Python do multica. Você cria issues num board estilo Linear, atribui a um agente (claude, devin, agy, opencode) e o agente trabalha na issue num workspace isolado, reportando progresso em tempo real via WebSocket. Humanos e agentes convivem no mesmo board, chat e inbox.

## Arquitetura

```
                          ┌──────────────────────────────────────────┐
                          │              Container Ryu               │
  Browser (HTMX/WS)       │                                          │
  ────────────────►  ┌────┴─────┐   ┌──────────┐   ┌──────────────┐  │
  /w/{slug}/...      │ FastAPI  │──►│ Services │──►│  SQLAlchemy  │  │
  /api/*             │ routers  │   │ (issues, │   │  async       │  │
  /ws                │          │   │  tasks,  │   │              │  │
                     └────┬─────┘   │  chat…)  │   └──────┬───────┘  │
                          │         └────┬─────┘          │          │
                     ┌────┴─────┐        │         ┌──────┴───────┐  │
                     │ Realtime │◄───────┤         │ SQLite /data │  │
                     │   Hub    │  hub.publish     │ (ou Postgres)│  │
                     └──────────┘        │         └──────────────┘  │
                                    ┌────┴───────────────┐           │
                                    │ Runner / Adapters  │           │
                                    │ claude, devin,     │           │
                                    │ agy, opencode      │           │
                                    │ /data/workspaces/* │           │
                                    └────────────────────┘           │
                          └──────────────────────────────────────────┘
```

- **API**: FastAPI, routers por domínio (`/api/auth`, `/api/issues`, `/api/agents`, `/api/tasks`, `/api/chat`, `/api/skills`, `/api/autopilots`, `/api/inbox`).
- **UI**: Jinja2 + HTMX + Tailwind (CDN), dark theme, páginas em `/w/{slug}/...`. Um design system (tema claro/escuro, accent ciano, ícones Lucide) está especificado em `docs/tailwind-config-mapping.md` e ainda em implantação.
- **Realtime**: hub in-memory por workspace (`issue:*`, `task:*`, `chat:*`, `inbox:new`, ...).
- **Runner**: fila de tasks em tabela; o servidor faz scheduler/sweeper/GC, e a execução acontece no Daemon (na máquina do usuário) — não há executor in-process (ADR-0001).
- **Banco**: SQLite (default, arquivo em `/data/ryu.db`) ou Postgres via `RYU_DATABASE_URL`.

## Build & Run

```bash
docker build -f deploy/Dockerfile -t ryu .

docker run -d --name ryu \
  -p 8000:8000 \
  -v ryu_data:/data \
  -e RYU_JWT_SECRET="troque-por-um-segredo-forte" \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  ryu
```

Acesse http://localhost:8000.

## Primeiro login

O Ryu usa login por código de verificação. Sem provedor de e-mail configurado, o código aparece **no log do container**:

```bash
docker logs -f ryu
# ... verification code for voce@exemplo.com: 483920
```

Digite o e-mail na tela de login, pegue o código no log e entre. Em desenvolvimento você pode fixar um código com `RYU_DEV_VERIFICATION_CODE=000000`.

## Criando um agent e atribuindo uma issue

1. Entre no workspace e vá em **Agents → New Agent**.
2. Escolha o Provider (`claude`, `devin`, `agy` ou `opencode`), dê um nome e salve. O agente vira um "membro" do workspace.
3. Crie uma issue no board (`/w/{slug}/board`) e no campo **Assignee** selecione o agente.
4. Ao mover a issue para *Todo*/*In Progress* (ou usar "Run"), uma task é enfileirada; o runner despacha para a CLI do agente num workspace em `/data/workspaces/<issue>`.
5. Acompanhe o progresso em tempo real na página da issue (eventos `task:running`, `task:progress`, `task:completed`).

Via API:

```bash
curl -X POST localhost:8000/api/agents -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "dev-bot", "runtime": "claude"}'
curl -X POST localhost:8000/api/issues -H "Authorization: Bearer $TOKEN" \
  -d '{"title": "Corrigir bug X", "assignee_type": "agent", "assignee_id": "<agent_id>"}'
```

## Variáveis de ambiente

Prefixo `RYU_` (via pydantic-settings; `.env` também funciona):

| Variável | Default | Descrição |
|---|---|---|
| `RYU_DATABASE_URL` | `sqlite+aiosqlite:////data/ryu.db` | SQLite é o default no container. Para Postgres: `postgresql+asyncpg://user:pass@host/ryu` |
| `RYU_JWT_SECRET` | `change-me` | **Obrigatório em produção.** Assina os tokens de sessão |
| `RYU_DATA_DIR` | `/data` | Raiz de dados persistentes (monte um volume aqui) |
| `RYU_WORKSPACES_ROOT` | `/data/workspaces` | Workspaces de trabalho dos agentes |
| `RYU_UPLOADS_DIR` | `/data/uploads` | Uploads/anexos |
| `RYU_ALLOW_SIGNUP` | `true` | Permite cadastro de novos usuários |
| `RYU_DEV_VERIFICATION_CODE` | — | Se setado, esse código de login é sempre aceito (dev) |
| `RYU_LITELLM_MODEL` | `anthropic/claude-3-5-haiku-20241022` | Modelo para títulos de chat etc. |
| `RYU_PORT` | `8000` | Porta HTTP |
| `ANTHROPIC_API_KEY` | — | Repassada à CLI `claude` (agentes claude) |

## Banco de dados

- **SQLite** (default): zero configuração, arquivo em `/data/ryu.db` dentro do volume. Bom para nó único / uso pessoal e times pequenos.
- **Postgres** (opcional): aponte `RYU_DATABASE_URL` para `postgresql+asyncpg://...`; o driver `asyncpg` já vem instalado. Recomendado para produção com mais carga.

## Roadmap

- Integração **GitHub** (issues bidirecional, PRs abertos por agentes) e **Slack** (notificações, chat de agente em canal).
- **Postgres** como caminho de produção documentado com migrações (Alembic).
- **Multi-nó**: hub realtime distribuído (Redis pub/sub) e fila de tasks compartilhada para escalar runners horizontalmente.
- Mais adapters de agente e marketplace de skills.


## Documentação

- [docs/DEPLOY.md](docs/DEPLOY.md) — deploy e operação
- [docs/PARITY.md](docs/PARITY.md) — paridade funcional com o multica
- [docs/CONTRACTS.md](docs/CONTRACTS.md) — contratos internos do codebase
- [docs/ryu-plano-stack.md](docs/ryu-plano-stack.md) — plano original e decisões de stack
