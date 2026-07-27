"""Alternância de tema claro/escuro (#30).

A mecânica decidida em #10: o cookie `ryu_theme` é lido no servidor e o
`data-theme` sai correto já no primeiro HTML — sem flash e sem script
bloqueante no `<head>`. Sem cookie, claro.
"""
from __future__ import annotations

import pytest

from .conftest import TEMPLATES, FakeRequest, render

BASE_HTML = TEMPLATES / "base.html"
PROFILE_HTML = TEMPLATES / "workspace/profile.html"


_CTX = {
    "workspace": {"slug": "ws", "id": "ws-1", "name": "Workspace"},
    "user": {"id": "u1", "name": "Dev", "email": "dev@example.com"},
}


def _base(cookies=None):
    return render(_ENV, "base.html", _CTX, request=FakeRequest(cookies))


@pytest.fixture(scope="module", autouse=True)
def _bind_env(env):
    global _ENV
    _ENV = env


# ── Default e leitura do cookie ──────────────────────────────────────────────


def test_no_cookie_renders_light():
    """Decisão do #10: sem cookie, o padrão é claro."""
    assert 'data-theme="light"' in _base()


def test_cookie_dark_renders_dark():
    assert 'data-theme="dark"' in _base({"ryu_theme": "dark"})


def test_cookie_light_renders_light():
    assert 'data-theme="light"' in _base({"ryu_theme": "light"})


@pytest.mark.parametrize("value", ["", "DARK", "escuro", "true", "1", "dark ", "auto"])
def test_unrecognised_cookie_falls_back_to_light(value):
    """Só 'dark' liga o escuro; o resto cai no :root, que é claro."""
    assert 'data-theme="light"' in _base({"ryu_theme": value})


def test_cookie_cannot_inject_into_the_attribute():
    """O valor nunca é interpolado cru — atributo só pode ser light ou dark."""
    html = _base({"ryu_theme": '" onload="alert(1)'})
    assert "onload" not in html
    assert 'data-theme="light"' in html


# ── Sem FOUC ─────────────────────────────────────────────────────────────────


def test_theme_is_decided_server_side_not_by_script():
    """Nada de script no <head> decidindo tema — é o que causa flash."""
    head = BASE_HTML.read_text().split("</head>")[0]
    for smell in ("localStorage", "prefers-color-scheme", "documentElement.setAttribute"):
        assert smell not in head, f"{smell} no <head> reintroduz risco de FOUC"


def test_html_tag_carries_the_attribute_before_any_stylesheet():
    """O data-theme precisa estar no <html>, antes do CSS, pro primeiro paint."""
    raw = BASE_HTML.read_text()
    open_tag = raw[raw.index("<html") : raw.index(">", raw.index("<html")) + 1]
    assert "data-theme=" in open_tag, f"<html> sem data-theme: {open_tag}"
    assert raw.index("<html") < raw.index('href="/static/app.css"')


# ── Toggle no Profile ────────────────────────────────────────────────────────


def _profile(cookies=None):
    ctx = dict(_CTX, active_nav="profile", saved=None)
    return render(_ENV, "workspace/profile.html", ctx, request=FakeRequest(cookies))


def test_profile_offers_the_opposite_theme():
    assert "Usar tema escuro" in _profile()
    assert "Usar tema claro" in _profile({"ryu_theme": "dark"})


def test_profile_reports_the_current_theme():
    assert "Tema atual: claro" in _profile()
    assert "Tema atual: escuro" in _profile({"ryu_theme": "dark"})


def test_toggle_button_points_at_the_text_that_states_the_theme():
    """`aria-pressed` mentia no escuro: o nome do botão oferecia "Usar tema
    claro" enquanto `pressed=true` se referia ao escuro — o leitor de tela
    anunciava "Usar tema claro, pressionado". O estado passa a vir do texto ao
    lado, ligado por `aria-describedby`; substitui o `aria-pressed` que a #50
    pedia ao pé da letra.
    """
    assert "aria-pressed" not in _profile()
    for cookies, current in ((None, "claro"), ({"ryu_theme": "dark"}, "escuro")):
        html = _profile(cookies)
        assert 'aria-describedby="theme-state"' in html
        assert 'id="theme-state"' in html
        assert f"Tema atual: {current}" in html


def test_toggle_writes_the_cookie_the_server_reads():
    js = PROFILE_HTML.read_text()
    assert "ryu_theme=" in js
    assert "path=/" in js
    assert "samesite=lax" in js
    # sem max-age o cookie é de sessão e a escolha morre ao fechar o browser
    assert "max-age=31536000" in js


def test_toggle_lives_in_profile_not_in_the_chrome():
    """O tema é do usuário (#50), então o botão mora no Profile — mas a decisão
    do #10 de manter o alternador fora da sidebar/topbar continua valendo."""
    assert "ryuToggleTheme" not in BASE_HTML.read_text()
    assert "ryuToggleTheme" in PROFILE_HTML.read_text()
