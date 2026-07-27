"""Registro único dos Providers suportados pelo Ryu (issue #55).

Provider é a família de CLI de agente que um Runtime expõe. Adicionar um
Provider é editar `PROVIDERS` — e só. Antes desta lista existiam quatro
paralelas (agentes suportados, famílias de protocolo, catálogo de modelos e
comandos de update) e nenhuma delas estava completa.

Suportados: claude, devin, agy e opencode. Saíram codex, gemini, copilot,
cursor-agent e qwen — sem migração e sem alias: agentes que os usavam falham
com razão `provider_unsupported`.

`acp` segue o ADR-0002 (`claude --acp`, `devin acp`, `opencode acp`); o `agy`
é o único no caminho legado de prompt único. `update` é o subcomando de
self-update do próprio CLI (None = atualiza pelo instalador).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    binary: str
    env_key: str  # overrides RYU_<env_key>_PATH/_MODEL/_ARGS
    description: str
    install: dict[str, str]  # sys.platform ("darwin"|"win32"|"linux") -> comando
    acp: bool
    update: list[str] | None


PROVIDERS: dict[str, Provider] = {
    "claude": Provider(
        name="claude",
        binary="claude",
        env_key="CLAUDE",
        description="Anthropic Claude Code",
        install={
            "darwin": "curl -fsSL https://claude.ai/install.sh | bash",
            "linux": "curl -fsSL https://claude.ai/install.sh | bash",
            "win32": "irm https://claude.ai/install.ps1 | iex",
        },
        acp=True,
        update=["update"],
    ),
    "devin": Provider(
        name="devin",
        binary="devin",
        env_key="DEVIN",
        description="Cognition Devin CLI",
        install={
            "darwin": "curl -fsSL https://cli.devin.ai/install.sh | bash",
            "linux": "curl -fsSL https://cli.devin.ai/install.sh | bash",
            "win32": "irm https://static.devin.ai/cli/setup.ps1 | iex",
        },
        acp=True,
        update=None,
    ),
    "agy": Provider(
        name="agy",
        binary="agy",
        env_key="AGY",
        description="Google Antigravity CLI",
        install={
            "darwin": "curl -fsSL https://antigravity.google/cli/install.sh | bash",
            "linux": "curl -fsSL https://antigravity.google/cli/install.sh | bash",
            "win32": "irm https://antigravity.google/cli/install.ps1 | iex",
        },
        acp=False,
        update=None,
    ),
    "opencode": Provider(
        name="opencode",
        binary="opencode",
        env_key="OPENCODE",
        description="OpenCode",
        install={
            "darwin": "curl -fsSL https://opencode.ai/install | bash",
            "linux": "curl -fsSL https://opencode.ai/install | bash",
            "win32": "npm install -g opencode-ai",
        },
        acp=True,
        update=["upgrade"],
    ),
}

NAMES = tuple(PROVIDERS)


def get(name: str) -> Provider | None:
    return PROVIDERS.get(name)


def is_supported(name: str) -> bool:
    return name in PROVIDERS


def install_command(name: str, platform: str | None = None) -> str | None:
    """Comando de instalação do Provider na plataforma do Device."""
    spec = PROVIDERS.get(name)
    if spec is None:
        return None
    return spec.install.get(platform or sys.platform)
