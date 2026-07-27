from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Ryu"
    database_url: str = "sqlite+aiosqlite:////data/ryu.db"
    jwt_secret: str = "change-me"
    data_dir: Path = Path("/data")
    workspaces_root: Path = Path("/data/workspaces")
    uploads_dir: Path = Path("/data/uploads")
    allow_signup: bool = True
    # allowlists de signup (paridade multica ALLOWED_EMAILS / ALLOWED_EMAIL_DOMAINS)
    # listas separadas por vírgula, case-insensitive. Precedência: e-mail > domínio > allow_signup;
    # allowlist configurada sem match bloqueia mesmo com allow_signup=true.
    allowed_emails: str = ""
    allowed_email_domains: str = ""
    dev_verification_code: str | None = None  # se setado, aceita esse código sempre
    # workspace-auth ciclo 1 — criação de workspaces adicionais (multica DISABLE_WORKSPACE_CREATION)
    disable_workspace_creation: bool = False
    # convites: validade padrão de um convite pendente
    invitation_ttl_days: int = 7

    # ── Auth hardening (workspace-auth ciclo 1) ───────────────────────
    auth_code_resend_seconds: int = 60  # cooldown por e-mail no request-code
    rate_limit_auth: int = 5  # req/min por IP em request-code|google (0 = off)
    rate_limit_auth_verify: int = 20  # req/min por IP no verify (0 = off)

    # ── Google OAuth (workspace-auth ciclo 1) — ativado por env var ───
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None

    # ── E-mail (workspace-auth ciclo 1) — SMTP relay > Resend > stdout ─
    smtp_host: str | None = None
    smtp_port: int = 25
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_tls: str = ""  # starttls|implicit|smtps|ssl ("" = starttls; porta 465 força implicit)
    smtp_ehlo_name: str | None = None
    resend_api_key: str | None = None
    resend_from_email: str | None = None
    litellm_model: str = "anthropic/claude-3-5-haiku-20241022"  # títulos de chat etc.
    port: int = 8000

    # ── LLM auxiliar (títulos de chat etc.) — ativado por env var ─────
    # RYU_ANTHROPIC_API_KEY ou RYU_OPENAI_API_KEY; sem chave = no-op/fallback.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"  # p/ proxies OpenAI-compat
    llm_timeout_seconds: float = 15.0

    # ── Chat ──────────────────────────────────────────────────────────
    chat_pinned_agents_cap: int = 8  # cap de pins da barra de quick-agents

    # ── Attachments / storage ─────────────────────────────────────────
    # "auto": usa S3 se s3_bucket + credenciais configurados; senão disco local.
    attachment_storage: str = "auto"  # auto|local|s3
    attachment_max_size_bytes: int = 100 * 1024 * 1024  # 100 MB (paridade multica)
    attachment_download_url_ttl: int = 1800  # segundos (presigned GET)
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_endpoint: str | None = None  # p/ R2 / MinIO; default AWS
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_public_base_url: str | None = None  # CDN público (opcional)

    # ── Runner / fila de tasks (agents-tasks ciclo 1) ─────────────────
    # O servidor NÃO executa tasks; o Daemon é o único executor (ADR-0001).
    # O runner mantém scheduler, sweeper de lease, TTL de fila, retry e GC de work_dir.
    task_lease_minutes: int = 30  # lease renovado a cada heartbeat do daemon
    task_queued_ttl_hours: int = 24  # TTL de task presa em queued
    task_default_max_attempts: int = 3  # retries automáticos p/ falha de infra
    sweep_interval_seconds: int = 60  # sweeper de órfãs/leases vencidos
    workdir_gc_days: int = 7  # GC de work_dirs de tasks terminadas
    workdir_gc_interval_seconds: int = 3600

    # ── Autopilots / webhooks (autopilots-skills ciclo 1) ─────────────
    webhook_body_max_bytes: int = 256 * 1024  # cap do corpo no ingress (paridade multica)
    webhook_payload_prompt_max_chars: int = 8000  # payload truncado no prompt/issue

    # ── Skills locais do runtime (autopilots-skills ciclo 1) ──────────
    # Diretório varrido por GET /api/skills/local-runtime (default: ~/.claude/skills).
    local_skills_dir: Path | None = None

    # ── Daemon externo / CLI (daemon-cli ciclo 1) ─────────────────────
    daemon_token_ttl_days: int = 30  # validade do rdt_ emitido no register
    runtime_offline_seconds: int = 60  # sem heartbeat há N s → runtime offline
    app_url: str | None = None  # URL pública do app (fluxo de login do CLI)

    # ── Usage observability ciclo 1 ───────────────────────────────────
    usage_rollup_interval_seconds: int = 60  # cadência do job incremental de rollup
    metrics_enabled: bool = True  # RYU_METRICS_ENABLED=false desliga /metrics (404)
    readiness_cache_seconds: float = 5.0  # cache curto do /readyz p/ não martelar o DB

    # ── Integrations (integrations ciclo 1) ───────────────────────────
    # Chave usada p/ criptografar tokens/secrets de integrações no banco
    # (ryu.services.crypto). Fallback: jwt_secret.
    integrations_secret_key: str | None = None

    # GitHub App — desativado (no-op/log) enquanto github_app_id não setado.
    github_app_id: str | None = None
    github_app_private_key: str | None = None  # PEM
    github_app_client_id: str | None = None
    github_app_client_secret: str | None = None
    github_app_slug: str | None = None  # p/ montar a URL pública de instalação
    github_webhook_secret: str | None = None  # HMAC do X-Hub-Signature-256
    github_api_base_url: str = "https://api.github.com"

    # VCS self-hosted (Forgejo/Gitea/GitLab) — não precisa de env global;
    # cada VcsConnection guarda seu próprio base_url/token/webhook_secret.
    vcs_check_snapshot_ttl_seconds: int = 300

    # Slack — BYO por workspace (installation guarda os tokens); estes envs
    # só habilitam a feature em si (permitem desativar globalmente).
    slack_enabled: bool = True
    slack_api_base_url: str = "https://slack.com/api"

    # Lark/Feishu — BYO por workspace; região escolhida por installation.
    lark_enabled: bool = True

    model_config = {"env_prefix": "RYU_", "env_file": ".env"}


settings = Settings()
