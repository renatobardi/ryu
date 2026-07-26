"""A migração para o vocabulário semântico cobre todos os templates.

Portão de conjunto: só passa quando a última tela migrar, e por isso não
podia viver em nenhuma das PRs de tela individualmente (#24-#28). Existe
para que a próxima tela não reintroduza cor crua sem que ninguém perceba.
"""
from __future__ import annotations

import pytest

from .conftest import LEGACY_VOCABULARY, TEMPLATES


_TEMPLATE_FILES = sorted(TEMPLATES.rglob("*.html"))


def test_there_are_templates_to_check():
    """Guarda contra o glob silenciosamente não achar nada."""
    assert len(_TEMPLATE_FILES) > 20


@pytest.mark.parametrize("path", _TEMPLATE_FILES, ids=lambda p: str(p.name))
def test_template_carries_no_legacy_vocabulary(path):
    html = path.read_text()
    for token in LEGACY_VOCABULARY:
        assert token not in html, f"{token!r} em {path.relative_to(TEMPLATES)}"


def test_app_css_has_no_bespoke_status_classes():
    css = (TEMPLATES.parent / "static/app.css").read_text()
    for prefix in (".ryu-status-", ".ryu-agent-", ".ryu-task-", ".ryu-sev-"):
        assert prefix not in css, f"{prefix} ainda em app.css"
