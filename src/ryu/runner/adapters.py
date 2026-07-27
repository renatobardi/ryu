"""Adapters de runtime: constroem o comando do CLI de agente.

Defaults seguros: NENHUMA flag de bypass de permissão é adicionada
automaticamente. Se você quer execução totalmente autônoma, adicione as
flags você mesmo em agent.runtime_config["extra_args"] (escolha consciente).

runtime_config suportado:
  extra_args: list[str]  — flags extras (ex.: modos de permissão)
  command:    list[str]  — comando totalmente customizado; "{prompt}" é substituído
  env:        dict       — env extra para o processo
  repo_url:   str        — git clone no workspace antes de rodar

Extensões (ciclo 1):
  model / instructions / resume_session_id / structured — configuração do
  agente aplicada ao run (multica 021/050); profile — runtime_profile
  compartilhado do workspace (multica 120): command_name substitui o binário
  e fixed_args entram antes dos extra_args do agente.

Extensões (daemon-cli ciclo 1):
  - Detecção ampla de CLIs (multica 'Supported Agents'): claude, codex,
    gemini, opencode, copilot, cursor-agent, qwen (ACP-only ficam de fora).
  - Overrides por env: RYU_<AGENT>_PATH / RYU_<AGENT>_MODEL / RYU_<AGENT>_ARGS
    (ARGS com parsing shellword POSIX via shlex).
  - detect_runtimes(): enumera cada CLI detectado como runtime disponível
    (usado pela página de runtimes e pelo daemon no register).
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess

# runtimes com protocolo conhecido (também limita runtime_profile.protocol_family)
PROTOCOL_FAMILIES = ("claude", "codex", "gemini", "opencode", "copilot", "cursor-agent", "qwen")

# provider -> (binário default, env-key p/ overrides RYU_<KEY>_PATH/_MODEL/_ARGS)
SUPPORTED_AGENTS: dict[str, dict] = {
    "claude": {"binary": "claude", "env_key": "CLAUDE", "description": "Anthropic Claude Code"},
    "codex": {"binary": "codex", "env_key": "CODEX", "description": "OpenAI Codex CLI"},
    "gemini": {"binary": "gemini", "env_key": "GEMINI", "description": "Google Gemini CLI"},
    "opencode": {"binary": "opencode", "env_key": "OPENCODE", "description": "OpenCode"},
    "copilot": {"binary": "copilot", "env_key": "COPILOT", "description": "GitHub Copilot CLI"},
    "cursor-agent": {"binary": "cursor-agent", "env_key": "CURSOR", "description": "Cursor Agent"},
    "qwen": {"binary": "qwen", "env_key": "QWEN", "description": "Alibaba Qwen Code"},
}

THINKING_TOKENS = {"none": "0", "low": "4000", "medium": "10000", "high": "31999"}


def _env(name: str) -> str | None:
    v = os.environ.get(name, "").strip()
    return v or None


def agent_env_overrides(provider: str) -> dict:
    """Overrides por env do provider: {"path", "model", "args"} (multica
    MULTICA_<AGENT>_PATH/_MODEL/_ARGS → RYU_<AGENT>_PATH/_MODEL/_ARGS)."""
    spec = SUPPORTED_AGENTS.get(provider)
    if spec is None:
        return {}
    key = spec["env_key"]
    raw_args = _env(f"RYU_{key}_ARGS")
    args: list[str] = []
    if raw_args:
        try:
            args = shlex.split(raw_args)  # parsing shellword POSIX
        except ValueError:
            args = raw_args.split()
    return {
        "path": _env(f"RYU_{key}_PATH"),
        "model": _env(f"RYU_{key}_MODEL"),
        "args": args,
    }


def resolve_binary(provider: str) -> str | None:
    """Caminho do binário do provider (override RYU_<X>_PATH > PATH), ou None."""
    spec = SUPPORTED_AGENTS.get(provider)
    if spec is None:
        return shutil.which(provider)
    override = agent_env_overrides(provider).get("path")
    if override:
        return override if os.path.exists(override) else None
    return shutil.which(spec["binary"])


def _probe_version(path: str) -> str:
    try:
        out = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=5
        )
        line = (out.stdout or out.stderr or "").strip().splitlines()
        return line[0][:80] if line else ""
    except Exception:
        return ""


def detect_runtimes(with_version: bool = False) -> list[dict]:
    """Enumera os CLIs de agente detectados na máquina.

    Retorna [{provider, binary, path, available, model_override, version?}].
    Cada CLI detectado é um runtime registrável (não fallback p/ stub).
    """
    result = []
    for provider, spec in SUPPORTED_AGENTS.items():
        path = resolve_binary(provider)
        entry = {
            "provider": provider,
            "binary": spec["binary"],
            "description": spec["description"],
            "path": path,
            "available": path is not None,
            "model_override": agent_env_overrides(provider).get("model"),
        }
        if with_version and path:
            entry["version"] = _probe_version(path)
        result.append(entry)
    return result


def build_command(
    runtime: str,
    prompt: str,
    config: dict,
    *,
    model: str | None = None,
    instructions: str | None = None,
    resume_session_id: str | None = None,
    structured: bool = False,
    profile: dict | None = None,
) -> list[str] | None:
    """Retorna o argv para o runtime, ou None se a família do provider não é suportada.

    `profile` (opcional): {"protocol_family", "command_name", "fixed_args"} —
    resolve o comando a partir do runtime_profile do workspace.
    """
    if config.get("command"):
        return [prompt if part == "{prompt}" else part for part in config["command"]]

    family = runtime
    binary = None
    fixed: list[str] = []
    if profile:
        family = profile.get("protocol_family") or runtime
        binary = profile.get("command_name") or None
        fixed = list(profile.get("fixed_args") or [])

    if family not in PROTOCOL_FAMILIES:
        return None

    overrides = agent_env_overrides(family)
    binary = binary or overrides.get("path") or SUPPORTED_AGENTS.get(family, {}).get("binary") or family
    model = model or overrides.get("model")
    env_args = list(overrides.get("args") or [])

    if family == "claude":
        argv = [binary, "-p", prompt]
        if structured:
            argv += ["--output-format", "stream-json", "--verbose"]
        else:
            argv += ["--output-format", "text"]
        if model:
            argv += ["--model", model]
        if instructions:
            argv += ["--append-system-prompt", instructions]
        if resume_session_id:
            argv += ["--resume", resume_session_id]
    elif family == "codex":
        argv = [binary, "exec", prompt]
        if model:
            argv += ["-m", model]
        if resume_session_id:
            # codex >= 0.20: `codex exec resume <id>`; fallback conservador: ignora
            pass
    elif family == "opencode":
        argv = [binary, "run", prompt]
        if model:
            argv += ["-m", model]
    elif family == "copilot":
        argv = [binary, "-p", prompt]
        if model:
            argv += ["--model", model]
    elif family == "cursor-agent":
        argv = [binary, "-p", prompt, "--output-format", "text"]
        if model:
            argv += ["-m", model]
    elif family == "qwen":
        argv = [binary, "-p", prompt]
        if model:
            argv += ["-m", model]
    else:  # gemini
        argv = [binary, "-p", prompt]
        if model:
            argv += ["-m", model]

    if shutil.which(argv[0]) is None and not os.path.exists(argv[0]):
        return None
    return argv + fixed + env_args + list(config.get("extra_args") or [])


def runtime_env(
    runtime: str,
    *,
    thinking_level: str | None = None,
    service_tier: str | None = None,
) -> dict[str, str]:
    """Env vars derivadas da configuração do agente (thinking/service tier)."""
    env: dict[str, str] = {}
    if runtime == "claude":
        if thinking_level and thinking_level in THINKING_TOKENS:
            env["MAX_THINKING_TOKENS"] = THINKING_TOKENS[thinking_level]
        if service_tier:
            env["ANTHROPIC_SERVICE_TIER"] = service_tier
    return env
