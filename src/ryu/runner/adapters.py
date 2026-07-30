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
  agente aplicada ao run (multica 021/050).

Extensões (daemon-cli ciclo 1):
  - Os Providers vêm do registro único (ryu.providers): claude, devin, agy e
    opencode. Enquanto o cliente ACP não existe, só claude, opencode e agy
    têm caminho de prompt único; devin é ACP-only (ADR-0002).
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

from ryu import providers

THINKING_TOKENS = {"none": "0", "low": "4000", "medium": "10000", "high": "31999"}


def _env(name: str) -> str | None:
    v = os.environ.get(name, "").strip()
    return v or None


def agent_env_overrides(provider: str) -> dict:
    """Overrides por env do provider: {"path", "model", "args"} (multica
    MULTICA_<AGENT>_PATH/_MODEL/_ARGS → RYU_<AGENT>_PATH/_MODEL/_ARGS)."""
    spec = providers.get(provider)
    if spec is None:
        return {}
    raw_args = _env(f"RYU_{spec.env_key}_ARGS")
    args: list[str] = []
    if raw_args:
        try:
            args = shlex.split(raw_args)  # parsing shellword POSIX
        except ValueError:
            args = raw_args.split()
    return {
        "path": _env(f"RYU_{spec.env_key}_PATH"),
        "model": _env(f"RYU_{spec.env_key}_MODEL"),
        "args": args,
    }


def resolve_binary(provider: str) -> str | None:
    """Caminho do binário do provider (override RYU_<X>_PATH > PATH), ou None."""
    spec = providers.get(provider)
    if spec is None:
        return None
    override = agent_env_overrides(provider).get("path")
    if override:
        return override if os.path.exists(override) else None
    return shutil.which(spec.binary)


def resolution_failure(provider: str) -> tuple[str, str]:
    """(failure_reason, mensagem) quando o comando não pôde ser resolvido.

    Distingue as duas causas que antes colapsavam numa mensagem só: o Provider
    não é suportado pelo Ryu, ou o CLI dele não está instalado neste Device.
    """
    if not providers.is_supported(provider):
        return (
            "provider_unsupported",
            f"provider {provider} não é suportado pelo Ryu "
            f"(suportados: {', '.join(providers.NAMES)})",
        )
    if resolve_binary(provider) is None:
        return ("runtime_missing", f"CLI do provider {provider} não está instalado neste Device")
    # instalado, mas sem caminho de execução: ACP-only enquanto o cliente ACP não existe
    return ("runtime_missing", f"CLI do provider {provider} só fala ACP e o Daemon ainda não o implementa")


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
    for provider, spec in providers.PROVIDERS.items():
        path = resolve_binary(provider)
        entry = {
            "provider": provider,
            "binary": spec.binary,
            "description": spec.description,
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
) -> list[str] | None:
    """Retorna o argv para o runtime, ou None se ele não pode ser resolvido.

    None cobre duas causas — provider fora do registro e CLI ausente nesta
    máquina; use resolution_failure() para saber qual delas.
    """
    if config.get("command"):
        return [prompt if part == "{prompt}" else part for part in config["command"]]

    spec = providers.get(runtime)
    if spec is None:
        return None

    overrides = agent_env_overrides(runtime)
    binary = overrides.get("path") or spec.binary
    model = model or overrides.get("model")
    env_args = list(overrides.get("args") or [])

    if runtime == "claude":
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
    elif runtime == "opencode":
        argv = [binary, "run", prompt]
        if model:
            argv += ["-m", model]
    elif runtime == "agy":
        argv = [binary, "-p", prompt]
        if model:
            argv += ["-m", model]
    else:  # devin: só ACP (ADR-0002), sem caminho de prompt único
        return None

    if shutil.which(argv[0]) is None and not os.path.exists(argv[0]):
        return None
    return argv + env_args + list(config.get("extra_args") or [])


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
