"""Skills built-in da plataforma (paridade multica: task.go LoadAgentSkillBundles
+ builtin_skills.go).

Multica sempre acrescenta um conjunto fixo de skills de plataforma (ensinando
mentioning, autopilots, squads, etc.) por cima das skills de workspace de cada
agente, embutidas no binário em tempo de compilação. Este módulo é o
equivalente Ryu: os SKILL.md (+ arquivos de apoio) vivem em
``builtin_skills/<slug>/`` dentro do pacote e são lidos do disco (não há
embutimento em bytecode necessário — o pacote inteiro já viaja junto).

Layout: ``builtin_skills/<slug>/SKILL.md`` + arquivos opcionais. O ``<slug>``
carrega o prefixo ``ryu-`` para nunca colidir com o slug derivado do nome de
uma skill de workspace (ver runner/loop.py, que deriva o slug a partir de
``Skill.name``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent / "builtin_skills"


@dataclass
class BuiltinSkillFile:
    path: str
    content: str


@dataclass
class BuiltinSkill:
    slug: str
    content: str  # SKILL.md completo, já com frontmatter
    files: list[BuiltinSkillFile] = field(default_factory=list)


def load_builtin_skills() -> list[BuiltinSkill]:
    """Lê todos os diretórios builtin_skills/<slug>/ com um SKILL.md válido.

    Um diretório sem SKILL.md é ignorado silenciosamente (skill malformada)."""
    if not _ROOT.is_dir():
        return []
    out: list[BuiltinSkill] = []
    for entry in sorted(_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            continue
        content = skill_md.read_text(encoding="utf-8")
        files: list[BuiltinSkillFile] = []
        for p in sorted(entry.rglob("*")):
            if p.is_dir() or p == skill_md:
                continue
            rel = p.relative_to(entry).as_posix()
            try:
                files.append(BuiltinSkillFile(path=rel, content=p.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError):
                continue  # arquivo binário/ilegível: pula, nunca derruba o loader
        out.append(BuiltinSkill(slug=entry.name, content=content, files=files))
    return out
