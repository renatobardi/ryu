"""Adapters de runtime: constroem o comando do CLI de agente.

Defaults seguros: NENHUMA flag de bypass de permissão é adicionada
automaticamente. Se você quer execução totalmente autônoma, adicione as
flags você mesmo em agent.runtime_config["extra_args"] (escolha consciente).

runtime_config suportado:
  extra_args: list[str]  — flags extras (ex.: modos de permissão)
  command:    list[str]  — comando totalmente customizado; "{prompt}" é substituído
  env:        dict       — env extra para o processo
  repo_url:   str        — git clone no workspace antes de rodar
"""
from __future__ import annotations

import shutil


def build_command(runtime: str, prompt: str, config: dict) -> list[str] | None:
    """Retorna o argv para o runtime, ou None se o binário não existe (→ stub)."""
    if config.get("command"):
        return [prompt if part == "{prompt}" else part for part in config["command"]]

    extra = list(config.get("extra_args") or [])
    base: dict[str, list[str]] = {
        "claude": ["claude", "-p", prompt, "--output-format", "text"],
        "codex": ["codex", "exec", prompt],
        "gemini": ["gemini", "-p", prompt],
    }
    argv = base.get(runtime)
    if argv is None:
        return None
    if shutil.which(argv[0]) is None:
        return None
    return argv + extra
