# PARITY.md — Paridade Ryu ↔ multica (ciclo 1 + verificação final)

Este documento é o resultado do papel de **testador funcional final** do ciclo 1
de paridade: rodar a suíte, subir o servidor de verdade e percorrer via `curl`
o fluxo completo de um usuário, e registrar o que foi verificado. O ciclo 1
já tinha implementado os 116 gaps auditados; aqui não se redescobre — **verifica-se**.

## 1. Resultado da suíte de testes

```
cd /home/claude/ryu && .venv/bin/python -m pytest -q
90 passed
```

Nenhuma regressão. `tests/test_builtin_skills.py` + `src/ryu/runner/builtin_skills(.py/,/)`
estavam presentes como trabalho não commitado de um ciclo anterior (skills
built-in de plataforma, prefixo `ryu-`, entregues a todo agente por cima das
skills do workspace — paridade `task.go:3777 BuiltinSkills()`); validados e
mantidos.

## 2. Paridade por domínio

| Domínio | Paridade verificada neste ciclo | Limitações aceitas (fora de escopo) | Resultado do e2e |
|---|---|---|---|
| **Auth / Workspaces** | Login por código (dev code), cookie JWT httponly + CSRF de duplo-envio (`ryu_csrf` legível + header `X-CSRF-Token`), PATs (`ryu_*`) via `Authorization: Bearer`, convite de membro por e-mail com expiração | Google OAuth (código não testado sem client_id real, mas endpoint existe e falha 503 de forma correta sem config) | OK — login, `/api/auth/me`, criação de PAT e uso via Bearer, convite de workspace |
| **Projects** | CRUD de projeto, contagem de issues por projeto | — | OK — projeto criado e usado como `project_id` em issues |
| **Issues / Tracker** | Labels (criação/anexo), prioridade, sub-issue (`parent_issue_id`), busca (`/api/search`), comentários, activity log, board columns | `IssueDependency` (tabela `issue_dependencies` do schema multica) é **código morto no multica** — nenhum handler Go a referencia; não implementada em Ryu de propósito (não é gap real). Relação de precedência entre issues no Ryu é feita via sub-issue (`parent_issue_id`), que é o mecanismo real usado pelo multica (`issue_child_done.go`) | OK — issue com project+label+priority, sub-issue criada e listada em `/sub-issues` |
| **Agents / Tasks** | Runtime `command` explícito (bypassa runtimes reais, ex. `["echo","{prompt}"]`) além dos runtimes LLM (`claude`/`codex`/`opencode`/`copilot`), fila de tasks (queued→running→completed), comentário automático do agente + issue→`in_review` + inbox, permission_mode/invocation-targets | Execução real de Claude Code/Codex CLI requer os binários instalados (fora do escopo deste teste — usamos `runtime_config.command` para validar o pipeline completo sem depender de rede/CLI externo) | OK — task executada, comentário postado, issue em `in_review`, 2 notificações no inbox |
| **Chat** | Sessão de chat por agente, mensagem do usuário → task enfileirada → resposta do agente na mesma sessão | — | OK — sessão criada, mensagem enviada, resposta do agente presente em `/api/chat/{id}/messages` |
| **Skills** | Criação de skill, anexo a agente, injeção no workdir da task (`skills/<slug>/SKILL.md`) + skills built-in de plataforma sempre injetadas por cima | — | OK — skill criada e anexada ao agente via `POST /api/skills/{id}/agents/{agent_id}` |
| **Autopilots** | Autopilot manual (`trigger_type=manual`, `execution_mode=run_only`), disparo via `POST /{id}/run`, task enfileirada e completada | Triggers `cron`/`webhook` não exercidos neste e2e (cobertos por `test_autopilots_skills_cycle1.py`) | OK — autopilot criado e rodado, task associada completou |
| **Squads** | Não exercido neste e2e (fora do roteiro pedido) | — | Coberto por `test_chat_squads_cycle1.py` (não re-executado via curl) |
| **Usage / Observability** | `/api/dashboard/usage/daily`, `/usage/by-agent`, `/usage/by-hour`, `/api/dashboard/agent-task-snapshot`, `/api/dashboard/working-agents` (presença de agente — gap novo fechado neste ciclo), `/metrics` (Prometheus), rollups | `scope=mine`/relação "My Issues" do multica não tem equivalente em Ryu (documentado inline no código) | OK — todos os endpoints de dashboard retornaram 200; `/metrics` expõe `ryu_http_requests_total`, `ryu_build_info` etc. |
| **Integrations — GitHub App** | Webhook + espelho de PR (`GithubPullRequest`/`GithubCheckRun`), `GET /api/issues/{id}/pull-requests` (novo endpoint fechado neste ciclo, `router.go:1112`) | Poll ativo de checks via GraphQL/JWT RS256 (App auth) é limitação documentada e aceita — Ryu só espelha o último estado recebido via webhook | Não exercido no e2e (exige App/instalação reais); validado por `test_integrations_cycle1.py` |
| **Integrations — VCS self-hosted** (Forgejo/Gitea/GitLab) | `VcsConnection` por workspace com token/secret próprios, espelho de PR | Sem poll ativo (mesma limitação acima) | Coberto por testes; não exercido no e2e |
| **Integrations — Slack** | Instalação BYO, webhook `/api/webhooks/slack`, bind de usuário, roteamento real de mensagem → chat_session → agente → resposta de volta ao thread (`route_channel_message`, fechado neste ciclo) | Socket Mode não suportado — só HTTP/webhook (aceito) | Coberto por testes; não exercido no e2e (exige app Slack real) |
| **Integrations — Lark/Feishu** | Mesmo roteamento real de Slack, parse de `msg.content` JSON | WS (long-lived) não suportado — só HTTP/webhook (aceito) | Coberto por testes; não exercido no e2e |
| **Daemon / CLI** | Registro de runtime externo (`rdt_`), claim de tasks, heartbeat | — | Não exercido no e2e (fora do roteiro pedido); coberto por `test_daemon_cli_cycle1.py` |
| **Fora de escopo (aceito e documentado)** | — | Desktop/iOS, Redis/multi-nó, Fleet cloud, Composio | N/A |

## 3. Fluxo e2e — passo a passo

Ambiente: `RYU_DATABASE_URL=sqlite+aiosqlite:////tmp/e2efinal/ryu.db`,
`RYU_DATA_DIR=/tmp/e2efinal`, `RYU_WORKSPACES_ROOT=/tmp/e2efinal/ws`,
`RYU_UPLOADS_DIR=/tmp/e2efinal/up`, `RYU_DEV_VERIFICATION_CODE=123456`,
`RYU_JWT_SECRET=x`, porta 8031.

| # | Passo | Resultado |
|---|---|---|
| 1 | `POST /api/auth/request-code` + `POST /api/auth/verify` (código dev `123456`) | **OK** — cookies `ryu_auth`+`ryu_csrf` setados, workspace pessoal criado |
| 2 | `GET /api/auth/me` | **OK** |
| 3 | `POST /api/projects` ("Ryu E2E") | **OK** |
| 4 | `POST /api/issues/labels` ("bug") | **OK** |
| 5 | `POST /api/issues` (título, descrição, priority=high, project_id, label_ids) → RYU-1 | **OK** |
| 6 | `POST /api/issues` (sub-issue, parent_issue_id=RYU-1, priority=medium) → RYU-2; `GET /{id}/sub-issues` confirma vínculo | **OK** |
| 7 | `POST /api/agents` (runtime=claude, `runtime_config.command=["echo","{prompt}"]`) | **OK** |
| 8 | `PATCH /api/issues/{RYU-1}` (`status=todo`, `assignee_type=agent`, `assignee_id=<agent>`) → task enfileirada automaticamente | **OK** |
| 9 | Polling `GET /api/tasks?...` → task `completed`; `GET /api/issues/{id}` → `status=in_review`; `GET /{id}/comments` → comentário do agente; `GET /api/inbox` → 2 notificações (task pronta + novo comentário) | **OK** |
| 10 | `POST /api/chat/sessions` + `POST /{session}/messages` → task de chat enfileirada; `GET /{session}/messages` → resposta do agente presente | **OK** |
| 11 | `POST /api/skills` + `POST /api/skills/{id}/agents/{agent_id}` (anexar) | **OK** |
| 12 | `POST /api/autopilots` (trigger_type=manual, execution_mode=run_only, target_agent_id) + `POST /{id}/run` → task enfileirada e completada | **OK** |
| 13 | `GET /api/dashboard/usage/daily\|by-agent\|by-hour` → 200; `GET /api/dashboard/agent-task-snapshot` e `/working-agents` → 200; `GET /metrics` → métricas Prometheus presentes | **OK** |
| 14 | `POST /api/auth/tokens` (PAT) → usado com `Authorization: Bearer ryu_...` em `/api/auth/me` | **OK** |
| 15 | `POST /api/workspaces/{id}/members` (convite por e-mail) + `GET /{id}/invitations` | **OK** |
| 16 | `GET /api/search?q=e2e` → issues + chat session encontrados | **OK** |

Nenhuma falha real encontrada durante o e2e — nenhum código precisou ser
corrigido neste ciclo de verificação (a única "correção" foi confirmar que o
`IssueDependency` do multica é código morto e não representa um gap real,
conforme item 2 acima). Log do servidor sem exceptions/tracebacks durante
todo o fluxo. Servidor finalizado ao final do teste (`pkill -f "uvicorn ryu.main:app"`).

## 4. Variáveis de ambiente de integrações — o que cada credencial destrava

Prefixo `RYU_` em todas (`pydantic-settings`, `env_prefix="RYU_"`).

| Variável | Destrava |
|---|---|
| `RYU_GOOGLE_CLIENT_ID` / `RYU_GOOGLE_CLIENT_SECRET` / `RYU_GOOGLE_REDIRECT_URI` | Login "Entrar com Google" (`POST /api/auth/google`); sem elas o endpoint responde 503 |
| `RYU_SMTP_HOST`/`_PORT`/`_USERNAME`/`_PASSWORD`/`_FROM_EMAIL`/`_TLS`/`_TLS_INSECURE`/`_EHLO_NAME` | Envio de e-mail real (código de login, convite de workspace) via SMTP relay |
| `RYU_RESEND_API_KEY` / `RYU_RESEND_FROM_EMAIL` | Envio de e-mail via Resend (fallback se SMTP não configurado) |
| `RYU_DEV_VERIFICATION_CODE` | Código de verificação fixo para dev/testes (nunca usar em produção) |
| `RYU_ANTHROPIC_API_KEY` / `RYU_OPENAI_API_KEY` (+ `RYU_OPENAI_BASE_URL`) | LLM auxiliar (ex. geração de título de chat); sem chave, no-op/fallback |
| `RYU_S3_BUCKET` / `_REGION` / `_ENDPOINT` / `_ACCESS_KEY_ID` / `_SECRET_ACCESS_KEY` / `_PUBLIC_BASE_URL` | Storage de anexos em S3/R2/MinIO em vez de disco local (`RYU_ATTACHMENT_STORAGE=auto|local|s3`) |
| `RYU_GITHUB_APP_ID` / `_PRIVATE_KEY` / `_CLIENT_ID` / `_CLIENT_SECRET` / `_SLUG` / `RYU_GITHUB_WEBHOOK_SECRET` | Integração GitHub App (instalação, webhooks, espelho de PR/checks); sem `github_app_id` a integração fica em no-op/log |
| `RYU_INTEGRATIONS_SECRET_KEY` | Chave de criptografia dos tokens/secrets de integrações no banco (fallback: `RYU_JWT_SECRET`) |
| `RYU_SLACK_ENABLED` (default true) | Liga/desliga globalmente a feature Slack — cada workspace ainda faz BYO da própria instalação/tokens |
| `RYU_LARK_ENABLED` (default true) | Idem para Lark/Feishu |
| `RYU_LOCAL_SKILLS_DIR` | Diretório varrido por `GET /api/skills/local-runtime` (default `~/.claude/skills`) |
| `RYU_RUNNER_MODE` (`auto`\|`inprocess`\|`off`) | Controla se o runner in-process executa tudo, cede para daemons externos, ou não executa nada (só daemons via CLI) |
| `RYU_APP_URL` | URL pública usada em links de bind de canal (Slack/Lark) e fluxo de login do CLI |
| `RYU_METRICS_ENABLED` (default true) | Liga/desliga `/metrics` (404 quando false) |
| `RYU_FEATURE_FLAGS_FILE` (+ `FF_<KEY>=true|false|42%|variant`) | Feature flags estilo multica `pkg/featureflag` |
| `RYU_JWT_SECRET`, `RYU_DATABASE_URL`, `RYU_DATA_DIR`, `RYU_WORKSPACES_ROOT`, `RYU_UPLOADS_DIR` | Configuração básica obrigatória de qualquer deploy (segredo de sessão, DB, diretórios de dados/workspaces/uploads) |

## 5. Limitações aceitas (fora de escopo, documentadas — não são gaps)

- Desktop/iOS nativos
- Redis / múltiplos nós (Ryu é single-container)
- Fleet cloud
- Composio
- Slack Socket Mode / Lark WebSocket (só HTTP/webhook)
- Poll ativo de checks do GitHub via JWT RS256 (App auth) — Ryu espelha o último
  estado recebido por webhook, não faz polling ativo via GraphQL
- `IssueDependency`/`issue_dependencies` do multica — tabela presente no schema
  Go mas sem nenhum handler que a use; não é uma feature real no multica, logo
  não é um gap em Ryu
