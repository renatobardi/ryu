"""Design system token expand (#19): vocabulary exists without changing UI."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP_CSS = REPO / "src/ryu/web/static/app.css"
BASE_HTML = REPO / "src/ryu/web/templates/base.html"


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


def test_app_css_has_light_and_dark_custom_properties():
    css = APP_CSS.read_text()
    assert ":root {" in css
    assert '[data-theme="dark"] {' in css

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
        assert f"{token}:" in css, f"missing {token}"


def test_app_css_preserves_existing_ryu_classes():
    css = APP_CSS.read_text()
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
    missing = [c for c in expected if c not in css]
    assert not missing, f"missing .ryu-* classes: {missing}"


def test_base_html_uses_data_theme_dark_and_new_config():
    html = BASE_HTML.read_text()
    assert '<html' in html
    assert 'data-theme="dark"' in html
    assert "tailwind.config = {" in html
    assert "darkMode: ['selector', '[data-theme=\"dark\"]']" in html
    assert "'surface-card': 'var(--surface-card)'" in html
    assert "'status-in-progress': 'var(--status-in-progress)'" in html


def test_base_html_preserves_zinc_and_violet_palette():
    html = BASE_HTML.read_text()
    assert "zinc-" in html
    assert "violet-" in html


def test_semantic_class_resolves_to_dark_token_value():
    css = APP_CSS.read_text()
    root = _extract_block(css, ":root")
    dark = _extract_block(css, '[data-theme="dark"]')

    assert _resolve(dark, root, "--surface-card") == "#212121"
    assert _resolve(dark, root, "--status-in-progress") == "#eab308"
    assert _resolve(dark, root, "--accent") == "#5fc3dd"
