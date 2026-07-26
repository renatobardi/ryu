"""Config local do CLI/daemon do Ryu (~/.ryu) — paridade multica cmd_config.

Arquivo JSON por perfil:
  ~/.ryu/config.json                 (perfil default)
  ~/.ryu/profiles/<name>/config.json (perfis extras — multica Profiles)

Chaves: server_url, app_url, workspace_id, token.
Resolução de workspace: flag --workspace-id > env RYU_WORKSPACE_ID > config.
Resolução de token:     env RYU_TOKEN > config.
Resolução de server:    env RYU_URL > config server_url > http://localhost:8000.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_SERVER_URL = "http://localhost:8000"

CONFIG_KEYS = ("server_url", "app_url", "workspace_id", "token")


def config_dir(profile: str | None = None) -> Path:
    base = Path(os.environ.get("RYU_CONFIG_DIR", str(Path.home() / ".ryu")))
    if profile and profile != "default":
        return base / "profiles" / profile
    return base


def config_path(profile: str | None = None) -> Path:
    return config_dir(profile) / "config.json"


def load_config(profile: str | None = None) -> dict:
    path = config_path(profile)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (ValueError, OSError):
        return {}


def save_config(cfg: dict, profile: str | None = None) -> Path:
    path = config_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)  # token dentro — só o dono lê
    except OSError:
        pass
    return path


def set_value(key: str, value: str, profile: str | None = None) -> dict:
    if key not in CONFIG_KEYS:
        raise ValueError(f"chave desconhecida: {key} (válidas: {', '.join(CONFIG_KEYS)})")
    cfg = load_config(profile)
    cfg[key] = value
    save_config(cfg, profile)
    return cfg


def resolve_server_url(profile: str | None = None) -> str:
    return (
        os.environ.get("RYU_URL", "").strip()
        or load_config(profile).get("server_url", "").strip()
        or DEFAULT_SERVER_URL
    ).rstrip("/")


def resolve_app_url(profile: str | None = None) -> str:
    return (
        os.environ.get("RYU_APP_URL", "").strip()
        or load_config(profile).get("app_url", "").strip()
        or resolve_server_url(profile)
    ).rstrip("/")


def resolve_token(profile: str | None = None) -> str:
    return os.environ.get("RYU_TOKEN", "").strip() or load_config(profile).get("token", "").strip()


def resolve_workspace_id(flag_value: str | None = None, profile: str | None = None) -> str | None:
    """Precedência: flag > env RYU_WORKSPACE_ID > default do config."""
    if flag_value:
        return flag_value
    env = os.environ.get("RYU_WORKSPACE_ID", "").strip()
    if env:
        return env
    return load_config(profile).get("workspace_id") or None


# ── Daemon (pidfile / log) ────────────────────────────────────────────
def daemon_log_path(profile: str | None = None) -> Path:
    return config_dir(profile) / "daemon.log"


def daemon_pid_path(profile: str | None = None) -> Path:
    return config_dir(profile) / "daemon.pid"


def workspaces_root(profile: str | None = None) -> Path:
    env = os.environ.get("RYU_DAEMON_WORKSPACES_ROOT", "").strip()
    if env:
        return Path(env)
    return config_dir(profile) / "workspaces"
