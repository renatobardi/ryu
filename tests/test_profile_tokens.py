"""A seção de Personal Access Tokens do Profile (#50).

O PAT é emitido para um usuário e não tem vínculo com workspace, por isso a
seção migrou de Workspace settings para o Profile.

A lista é montada em JavaScript a partir de `/api/auth/tokens`, e a suíte não
tem runtime de JS: o que estes testes travam é o **contrato do markup** — os
seletores e as mensagens que o usuário lê. O comportamento do servidor está
coberto no seam HTTP, em `test_profile_page.py`.
"""
from __future__ import annotations

from .conftest import render

_CTX = {
    "workspace": {"slug": "ws", "id": "ws-1", "name": "Workspace", "issue_prefix": "RYU"},
    "user": {"id": "u1", "name": "Dev", "email": "dev@example.com"},
    "active_nav": "profile",
    "saved": False,
}


def _profile(env) -> str:
    return render(env, "workspace/profile.html", _CTX)


def test_the_section_creates_a_named_token(env):
    html = _profile(env)
    assert "Personal Access Tokens" in html
    assert 'id="pat-name"' in html
    assert "Criar token" in html


def test_the_token_name_input_has_an_accessible_name(env):
    """Placeholder não é rótulo — ele desaparece ao digitar. O campo Nome, na
    mesma página, resolve isso com <label for>; aqui o input divide uma linha
    flex com o botão, então o nome acessível vem por aria-label.
    """
    assert 'aria-label="Nome do token"' in _profile(env)


def test_the_page_warns_that_the_token_appears_only_once(env):
    """O token cru só existe na resposta do POST; depois dela, nunca mais."""
    assert "exibido uma única vez" in _profile(env)


def test_the_list_has_a_place_for_the_tokens(env):
    """A data de criação vem de /api/auth/tokens — o que a API devolve está
    coberto em test_profile_page.py.
    """
    html = _profile(env)
    assert 'id="pat-list"' in html
    assert "/api/auth/tokens" in html


def test_the_list_offers_revoking(env):
    assert "Revogar" in _profile(env)


def test_an_empty_list_says_so(env):
    """Lista vazia com mensagem explícita, não uma caixa vazia parecendo quebrada."""
    assert "Nenhum token ativo." in _profile(env)


def test_a_token_name_never_goes_through_innerhtml(env):
    """O nome do token vem do usuário: interpolado em innerHTML, um nome como
    `<img src=x onerror=…>` executa quando a lista redesenha. A trava é positiva
    — o nome tem que passar por textContent — porque proibir só o innerHTML
    passaria também se o bloco todo desaparecesse.
    """
    assert "name.textContent = t.name" in _profile(env)


def test_every_failed_call_has_something_to_say(env):
    """Criar, listar e revogar falham de formas diferentes e nenhuma pode ser
    silenciosa: sem mensagem, um POST recusado é indistinguível de nada ter
    acontecido, e um GET recusado, de "não há token".

    Quando a mensagem é limpa depende do JS rodando — fora do alcance daqui.
    """
    html = _profile(env)
    assert 'id="pat-error"' in html
    assert 'role="alert"' in html
    for message in (
        "Não foi possível criar o token.",
        "Não foi possível carregar os tokens.",
        "Não foi possível revogar o token.",
    ):
        assert message in html
