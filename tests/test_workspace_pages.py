"""Workspace pages use the semantic design-system vocabulary (#27)."""
from __future__ import annotations

import pytest

from .conftest import TEMPLATES, assert_no_legacy_vocabulary, render  # noqa: F401


_COMMON_CTX = {
    "workspace": {"slug": "ws", "id": "ws-1", "name": "Workspace", "issue_prefix": "RYU"},
    "user": {"id": "u1", "name": "Dev", "email": "dev@example.com"},
}

_STATUS_TITLES = {
    "backlog": "Backlog",
    "todo": "Todo",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "done": "Done",
    "blocked": "Blocked",
    "cancelled": "Cancelled",
}




def _settings_ctx(saved=False):
    return {
        **_COMMON_CTX,
        "active_nav": "settings",
        "saved": saved,
    }


def _profile_ctx(saved=False):
    return {
        **_COMMON_CTX,
        "active_nav": "profile",
        "saved": saved,
    }


def _members_ctx():
    return {
        **_COMMON_CTX,
        "active_nav": "members",
        "members": [
            ({"id": "m1", "role": "owner"}, {"id": "u1", "name": "Owner", "email": "owner@example.com"}),
            ({"id": "m2", "role": "member"}, {"id": "u2", "name": "Dev", "email": "dev@example.com"}),
        ],
        "invitations": [
            {
                "id": "inv1",
                "invitee_email": "invited@example.com",
                "role": "member",
                "expires_at": "2026-08-02",
            }
        ],
        "my_role": "owner",
        "is_admin": True,
    }


def _runtimes_ctx():
    return {
        **_COMMON_CTX,
        "active_nav": "runtimes",
        "runtimes": [
            {"name": "claude", "path": "/usr/local/bin/claude", "available": True},
            {"name": "git", "path": None, "available": False},
        ],
    }


def _search_ctx(q=""):
    return {
        **_COMMON_CTX,
        "active_nav": "search",
        "q": q,
        "issues": [
            {"id": "i1", "key": "RYU-1", "title": "First issue", "status": "todo", "priority": "high"}
        ],
        "agents": [{"id": "a1", "name": "Coder", "handle": "coder", "status": "working"}],
        "chats": [{"id": "c1", "title": "Chat one"}],
        "status_titles": _STATUS_TITLES,
    }


def _invite_ctx(*, status="pending", expired=False):
    return {
        **_COMMON_CTX,
        "invitation": {"id": "inv1", "status": status, "role": "member"},
        "invite_workspace": {"name": "Workspace", "slug": "ws"},
        "expired": expired,
    }


def _my_issues_ctx():
    grouped = {st: [] for st in _STATUS_TITLES}
    grouped["todo"] = [
        {"id": "i1", "key": "RYU-1", "title": "Task for me", "status": "todo", "priority": "medium"}
    ]
    return {
        **_COMMON_CTX,
        "active_nav": "my_issues",
        "total": 1,
        "grouped": grouped,
        "status_order": list(_STATUS_TITLES.keys()),
        "status_titles": _STATUS_TITLES,
    }


# ── Settings ────────────────────────────────────────────────────────────────


def test_settings_uses_semantic_vocabulary(env):
    html = render(env, "workspace/settings.html", _settings_ctx(saved=True))
    assert_no_legacy_vocabulary(html, "workspace/settings.html")
    assert "bg-accent hover:bg-accent-hover text-text-on-accent" in html
    assert "focus:border-border-focus" in html


def test_settings_keeps_form_max_width(env):
    html = render(env, "workspace/settings.html", _settings_ctx())
    assert "max-w-2xl" in html


def test_settings_is_titled_workspace_settings(env):
    """"Settings" sozinho é ambíguo agora que Profile existe (CONTEXT.md)."""
    html = render(env, "workspace/settings.html", _settings_ctx())
    assert "Workspace settings" in html


def test_settings_inputs_are_associated_with_their_labels(env):
    """Mesma trava do campo de nome no Profile: sem `for`/`id` o leitor de tela
    não sabe de qual campo é o rótulo.
    """
    html = render(env, "workspace/settings.html", _settings_ctx())
    for field in ("ws-name", "ws-issue-prefix"):
        assert f'<label for="{field}"' in html
        assert f'id="{field}"' in html


def test_the_nav_entry_carries_the_full_term(env):
    """CONTEXT.md põe "Workspace settings" no nav e manda evitar "Settings"
    sozinho. Renderizado a partir do Profile — cujo h1 é "Profile" — para que
    o acerto só possa vir do nav.
    """
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert "Workspace settings" in html


def test_settings_exposes_nothing_personal(env):
    """Trava do corte por escopo (#50): tema, tokens e sair são do Profile.

    `ryuLogout` sozinho não serve de asserção — a função é global, definida no
    base.html; o que não pode voltar para cá é a chamada.
    """
    html = render(env, "workspace/settings.html", _settings_ctx())
    for smell in (
        "ryuToggleTheme",
        "Tema atual",
        "Personal Access Tokens",
        "pat-name",
        "pat-list",
        "createPat",
        "loadPats",
        'onclick="ryuLogout()"',
    ):
        assert smell not in html, f"{smell!r} voltou para Workspace settings"


# ── Profile ─────────────────────────────────────────────────────────────────


def test_profile_uses_semantic_vocabulary(env):
    html = render(env, "workspace/profile.html", _profile_ctx(saved=True))
    assert_no_legacy_vocabulary(html, "workspace/profile.html")
    assert "bg-accent hover:bg-accent-hover text-text-on-accent" in html
    assert "focus:border-border-focus" in html
    assert "Sair (logout)" in html


def test_profile_keeps_form_max_width(env):
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert "max-w-2xl" in html


def test_profile_name_input_is_associated_with_its_label(env):
    """Sem `for`/`id` o leitor de tela não sabe que o rótulo é daquele campo."""
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert '<label for="profile-name"' in html
    assert 'id="profile-name"' in html


def test_profile_logout_button_calls_ryuLogout(env):
    """Sair migrou de Settings para Profile (#49): a ação é sobre o usuário."""
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert 'onclick="ryuLogout()"' in html


# ── Profile: Personal Access Tokens ─────────────────────────────────────────
# O PAT é emitido para um usuário, sem vínculo com workspace, então a seção
# migrou de Settings para Profile (#50). A lista é montada em JS a partir de
# /api/auth/tokens; sem runtime de JS na suíte, estes testes travam o contrato
# do markup (os seletores e os textos que o JS injeta), não o comportamento.


def test_profile_creates_a_named_token(env):
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert "Personal Access Tokens" in html
    assert 'id="pat-name"' in html
    assert "Criar token" in html
    assert "createPat()" in html


def test_profile_token_name_input_has_an_accessible_name(env):
    """Placeholder não é rótulo — ele desaparece ao digitar. O campo Nome, na
    mesma página, resolve isso com <label for>; aqui o input divide uma linha
    flex com o botão, então o nome acessível vem por aria-label.
    """
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert 'aria-label="Nome do token"' in html


def test_profile_shows_the_full_token_only_once(env):
    """O token cru só existe na resposta do POST — a página avisa isso."""
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert "exibido uma única vez" in html
    assert "d.token" in html


def test_profile_lists_active_tokens_with_the_creation_date(env):
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert 'id="pat-list"' in html
    assert "/api/auth/tokens" in html
    assert "t.created_at" in html


def test_profile_revokes_a_token_and_refreshes_the_list(env):
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert "Revogar" in html
    assert "'DELETE'" in html


def test_profile_says_so_when_there_is_no_token(env):
    """Lista vazia com mensagem explícita, não uma caixa vazia parecendo quebrada."""
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert "Nenhum token ativo." in html


def test_profile_never_puts_a_token_name_inside_innerhtml(env):
    """O nome do token vem do usuário: interpolado em innerHTML, um nome como
    `<img src=x onerror=…>` executa quando a lista redesenha.
    """
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert "innerHTML = `" not in html, "template string em innerHTML volta a interpolar o nome"
    assert "name.textContent = t.name" in html


def test_profile_only_refreshes_the_list_when_the_revoke_worked(env):
    """Redesenhar sem olhar a resposta do DELETE avisa que o token sumiu quando
    ele continua lá.
    """
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert "if (!r.ok) return patError" in html
    assert "Não foi possível revogar o token." in html


def test_profile_says_when_creating_a_token_failed(env):
    """Sem isso um POST recusado é indistinguível de nada ter acontecido."""
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert 'id="pat-error"' in html
    assert "Não foi possível criar o token." in html


def test_profile_says_when_the_list_could_not_load(env):
    """GET recusado deixando o `<ul>` vazio é indistinguível de "não há token" —
    o estado vazio existe justamente para a lista não parecer quebrada.
    """
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert "Não foi possível carregar os tokens." in html


def test_profile_clears_the_error_once_the_action_works(env):
    """Mensagem de falha pendurada ao lado de uma ação bem-sucedida mente."""
    html = render(env, "workspace/profile.html", _profile_ctx())
    assert html.count("clearPatError();") >= 2


# ── Members ─────────────────────────────────────────────────────────────────


def test_members_uses_semantic_vocabulary(env):
    html = render(env, "workspace/members.html", _members_ctx())
    assert_no_legacy_vocabulary(html, "workspace/members.html")
    assert "bg-accent hover:bg-accent-hover text-text-on-accent" in html


def test_members_invite_form_keeps_max_width(env):
    html = render(env, "workspace/members.html", _members_ctx())
    assert "max-w-3xl" in html


# ── Runtimes ────────────────────────────────────────────────────────────────


def test_runtimes_uses_semantic_vocabulary(env):
    html = render(env, "workspace/runtimes.html", _runtimes_ctx())
    assert_no_legacy_vocabulary(html, "workspace/runtimes.html")
    assert "disponível" in html
    assert "indisponível" in html


def test_runtimes_table_keeps_max_width(env):
    html = render(env, "workspace/runtimes.html", _runtimes_ctx())
    assert "max-w-2xl" in html


# ── Search ──────────────────────────────────────────────────────────────────


def test_search_uses_semantic_vocabulary(env):
    html = render(env, "workspace/search.html", _search_ctx(q="issue"))
    assert_no_legacy_vocabulary(html, "workspace/search.html")
    assert "focus:border-border-focus" in html


def test_search_keeps_input_max_width(env):
    html = render(env, "workspace/search.html", _search_ctx())
    assert "max-w-xl" in html


def test_search_results_fragment_uses_semantic_vocabulary(env):
    html = render(env, "workspace/_search_results.html", _search_ctx(q="issue"))
    assert_no_legacy_vocabulary(html, "workspace/_search_results.html")


def test_search_results_fragment_renders_issues_agents_chats(env):
    html = render(env, "workspace/_search_results.html", _search_ctx(q="issue"))
    assert "RYU-1" in html
    assert "First issue" in html
    assert "Coder" in html
    assert "@coder" in html
    assert "Chat one" in html


def test_search_results_fragment_shows_prompt_when_empty(env):
    html = render(env, "workspace/_search_results.html", _search_ctx(q=""))
    assert "Digite algo para buscar" in html


# ── Invite ──────────────────────────────────────────────────────────────────


def test_invite_uses_semantic_vocabulary(env):
    html = render(env, "workspace/invite.html", _invite_ctx())
    assert_no_legacy_vocabulary(html, "workspace/invite.html")
    assert "bg-accent" in html


@pytest.mark.parametrize("status", ["pending", "accepted", "declined"])
def test_invite_card_keeps_max_width_for_any_status(env, status):
    html = render(env, "workspace/invite.html", _invite_ctx(status=status))
    assert "max-w-md" in html


# ── My Issues ───────────────────────────────────────────────────────────────


def test_my_issues_uses_semantic_vocabulary(env):
    html = render(env, "workspace/my_issues.html", _my_issues_ctx())
    assert_no_legacy_vocabulary(html, "workspace/my_issues.html")
    assert "RYU-1" in html
    assert "Task for me" in html


def test_my_issues_renders_empty_state(env):
    ctx = _my_issues_ctx()
    ctx["grouped"] = {st: [] for st in _STATUS_TITLES}
    ctx["total"] = 0
    html = render(env, "workspace/my_issues.html", ctx)
    assert "Nenhuma issue atribuída" in html


# ── Route-level smoke ───────────────────────────────────────────────────────


async def test_search_route_returns_and_renders_results(client):
    from tests.conftest import login

    data = await login(client, "search-user@example.com")
    ws = data["workspaces"][0]

    r = await client.post(
        "/api/issues",
        json={
            "workspace_id": ws["id"],
            "title": "searchable issue",
            "description": "",
            "status": "backlog",
            "priority": "none",
        },
    )
    assert r.status_code == 201, r.text
    issue = r.json()

    r = await client.get(f"/w/{ws['slug']}/search", params={"q": "searchable"})
    assert r.status_code == 200, r.text
    assert issue["key"] in r.text
    for token in ("zinc-", "violet-"):
        assert token not in r.text, f"{token} found in search page response"

    r = await client.get(
        f"/w/{ws['slug']}/search",
        params={"q": "searchable"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200, r.text
    assert issue["key"] in r.text
    for token in ("zinc-", "violet-"):
        assert token not in r.text, f"{token} found in search fragment response"
