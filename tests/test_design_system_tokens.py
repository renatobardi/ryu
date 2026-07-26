"""Design system token expand (#19) and sidebar/topbar migration (#21)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
APP_CSS = REPO / "src/ryu/web/static/app.css"
BASE_HTML = REPO / "src/ryu/web/templates/base.html"
TEMPLATES = REPO / "src/ryu/web/templates"


@pytest.fixture(scope="module")
def app_css():
    return APP_CSS.read_text()


@pytest.fixture(scope="module")
def base_html():
    return BASE_HTML.read_text()


@pytest.fixture(scope="module")
def templates_text():
    return "\n".join(p.read_text() for p in TEMPLATES.rglob("*.html"))


def _extract_block(css: str, selector: str) -> dict[str, str]:
    """Extract a flat block of custom properties (no nested braces)."""
    pattern = re.compile(re.escape(selector) + r"\s*\{([^}]*)\}", re.DOTALL)
    match = pattern.search(css)
    assert match, f"{selector} block not found"
    props: dict[str, str] = {}
    for decl in match.group(1).split(";"):
        decl = decl.strip()
        if not decl or ":" not in decl:
            continue
        name, value = decl.split(":", 1)
        props[name.strip()] = value.strip()
    return props


def _resolve(props: dict[str, str], root: dict[str, str], name: str) -> str:
    """Resolve one level of var() references against root + dark props."""
    value = props.get(name) or root.get(name, "")
    m = re.fullmatch(r"var\((--[\w-]+)\)", value)
    if m:
        ref = m.group(1)
        return props.get(ref) or root.get(ref, value)
    return value


def test_app_css_has_light_and_dark_custom_properties(app_css):
    assert ":root {" in app_css
    assert '[data-theme="dark"] {' in app_css

    for token in [
        "--surface-app",
        "--surface-card",
        "--text-primary",
        "--text-body",
        "--accent",
        "--accent-hover",
        "--status-in-progress",
        "--status-done",
        "--agent-working-bg",
        "--agent-working-fg",
    ]:
        assert f"{token}:" in app_css, f"missing {token}"


def test_app_css_preserves_existing_ryu_classes(app_css):
    expected = [
        ".ryu-status-backlog",
        ".ryu-status-todo",
        ".ryu-status-in_progress",
        ".ryu-status-in_review",
        ".ryu-status-done",
        ".ryu-status-blocked",
        ".ryu-status-cancelled",
        ".ryu-agent-idle",
        ".ryu-agent-working",
        ".ryu-agent-blocked",
        ".ryu-agent-error",
        ".ryu-agent-offline",
        ".ryu-task-queued",
        ".ryu-task-dispatched",
        ".ryu-task-running",
        ".ryu-task-completed",
        ".ryu-task-failed",
        ".ryu-task-cancelled",
        ".ryu-sev-action_required",
        ".ryu-sev-attention",
        ".ryu-sev-info",
    ]
    missing = [c for c in expected if c not in app_css]
    assert not missing, f"missing .ryu-* classes: {missing}"


def test_base_html_uses_data_theme_dark_and_new_config(base_html):
    assert '<html' in base_html
    assert 'data-theme="dark"' in base_html
    assert "tailwind.config = {" in base_html
    assert "darkMode: ['selector', '[data-theme=\"dark\"]']" in base_html
    assert "'surface-card': 'var(--surface-card)'" in base_html
    assert "'status-in-progress': 'var(--status-in-progress)'" in base_html


def test_sidebar_topbar_no_legacy_palette_classes(base_html):
    # AC #21: sidebar e topbar não usam mais zinc/violet/hex arbitrário.
    for token in ("zinc-", "violet-", "neutral-", "#0b0b0f", "#0e0e13", "#111116"):
        assert token not in base_html, f"{token} found in base.html"


def test_pins_sidebar_uses_design_system():
    pins = (TEMPLATES / "pins" / "_sidebar.html").read_text()
    for token in ("zinc-", "violet-", "neutral-"):
        assert token not in pins, f"{token} found in pins/_sidebar.html"
    assert 'data-lucide="pin"' in pins


def test_sidebar_topbar_uses_lucide_and_no_visible_logout():
    # Ícones de navegação via Lucide; nenhum "Sair" visível na sidebar.
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    html = env.get_template("base.html").render(
        workspace={"slug": "ws", "id": "ws-1"},
        user={"name": "Dev", "email": "dev@example.com"},
    )
    assert "data-lucide" in html
    assert 'data-lucide="inbox"' in html
    assert 'data-lucide="bot"' in html
    assert 'data-lucide="user"' in html
    assert ">Sair<" not in html


def test_semantic_bg_surface_card_resolves_to_token_value(app_css, base_html):
    root = _extract_block(app_css, ":root")
    dark = _extract_block(app_css, '[data-theme="dark"]')

    # The tailwind config wires bg-surface-card -> var(--surface-card).
    assert "'surface-card': 'var(--surface-card)'" in base_html
    # Under dark theme the variable resolves to #212121.
    assert _resolve(dark, root, "--surface-card") == "#212121"
