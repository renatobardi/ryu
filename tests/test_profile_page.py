"""Profile: a conta do usuário, alcançada pelo rodapé da sidebar (#49).

Settings é do workspace; Profile é do usuário. Estes testes ficam no seam
HTTP — cliente ASGI sobre o app real — como os das páginas de members e de
busca, porque o que importa é o que a página responde para quem está logado.
"""
from __future__ import annotations

from .conftest import login


async def test_profile_page_shows_the_logged_in_email(client):
    data = await login(client, "profile@example.com")
    slug = data["workspaces"][0]["slug"]

    r = await client.get(f"/w/{slug}/profile")

    assert r.status_code == 200, r.text
    assert "profile@example.com" in r.text
    # a página herda o chrome do workspace — é o motivo de morar sob /w/{slug}
    assert "Agentic issue tracking" in r.text


async def test_sidebar_footer_leads_to_profile(client):
    """O rodapé é a porta da conta; antes ele caía em Settings do workspace."""
    data = await login(client, "footer@example.com")
    slug = data["workspaces"][0]["slug"]

    r = await client.get(f"/w/{slug}/board")

    assert r.status_code == 200, r.text
    # o destino do rodapé sai escapado pelo Jinja (aspas simples viram &#39;)
    assert f"window.location.href=&#39;/w/{slug}/profile&#39;" in r.text
    assert f"window.location.href=&#39;/w/{slug}/settings&#39;" not in r.text


async def test_saving_a_new_name_persists_and_confirms(client):
    data = await login(client, "rename@example.com")
    slug = data["workspaces"][0]["slug"]

    r = await client.post(f"/w/{slug}/profile", data={"name": "Renato Bardi"})

    assert r.status_code == 303, r.text
    assert r.headers["location"] == f"/w/{slug}/profile?saved=1"

    r = await client.get(r.headers["location"])
    assert "Renato Bardi" in r.text
    assert "Alterações salvas." in r.text


async def test_a_blank_name_never_replaces_the_current_one(client):
    """`required` no HTML é só client-side; a recusa tem que ser no servidor."""
    data = await login(client, "blank@example.com")
    slug = data["workspaces"][0]["slug"]
    await client.post(f"/w/{slug}/profile", data={"name": "Renato Bardi"})

    await client.post(f"/w/{slug}/profile", data={"name": "   "})

    r = await client.get(f"/w/{slug}/profile")
    assert "Renato Bardi" in r.text


async def test_the_new_name_reaches_the_sidebar_footer_without_relogin(client):
    """O rodapé mostra o nome do usuário; o JWT só carrega o id, então a
    edição vale na hora. Guarda contra alguém passar a montar o User a
    partir do token."""
    data = await login(client, "sidebar@example.com")
    slug = data["workspaces"][0]["slug"]

    await client.post(f"/w/{slug}/profile", data={"name": "Nome Novo"})

    r = await client.get(f"/w/{slug}/board")
    assert "Nome Novo" in r.text


async def test_leaving_the_session_moved_to_profile(client):
    """Sair é ação sobre o usuário, não sobre o workspace."""
    data = await login(client, "logout@example.com")
    slug = data["workspaces"][0]["slug"]

    # a função vive no script global do base; o que muda de página é o botão
    r = await client.get(f"/w/{slug}/profile")
    assert 'onclick="ryuLogout()"' in r.text

    r = await client.get(f"/w/{slug}/settings")
    assert 'onclick="ryuLogout()"' not in r.text
