"""Projects, Pins e Login design-system migration (#28)."""
from __future__ import annotations

from .conftest import TEMPLATES, assert_no_legacy_vocabulary, render  # noqa: F401


_COMMON_CTX = {
    "workspace": {"slug": "ws", "id": "ws-1", "name": "Workspace"},
    "user": {"name": "Dev", "email": "dev@example.com"},
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


def _projects_ctx():
    return {
        **_COMMON_CTX,
        "active_nav": "projects",
        "projects": [
            {"id": "p1", "name": "Active", "status": "active", "description": "desc"},
            {"id": "p2", "name": "Archived", "status": "archived", "description": ""},
        ],
        "issue_counts": {"p1": 3, "p2": 0},
    }


def _project_detail_ctx():
    return {
        **_COMMON_CTX,
        "active_nav": "projects",
        "project": {"id": "p1", "name": "Active", "status": "active", "description": "desc"},
        "issues": [
            {"id": "i1", "key": "RYU-1", "title": "Issue one", "status": "in_progress"},
        ],
        "status_titles": _STATUS_TITLES,
    }


def _pins_ctx():
    return {
        **_COMMON_CTX,
        "pins": [
            {"item_type": "issue", "item": {"id": "i1", "key": "RYU-1", "title": "Issue one"}},
            {"item_type": "project", "item": {"id": "p1", "name": "Project one"}},
        ],
    }




def test_projects_index_uses_semantic_vocabulary(env):
    html = render(env, "projects/index.html", _projects_ctx())
    assert_no_legacy_vocabulary(html, "projects/index.html")
    # Project state comes from the status_pill macro with kind='state'.
    assert "bg-state-on-bg text-state-on-fg" in html
    assert "bg-state-off-bg text-state-off-fg" in html
    # Cards, inputs and primary button use semantic tokens.
    assert "bg-surface-card border border-border-default" in html
    assert "bg-surface-input border border-border-strong" in html
    assert "bg-accent hover:bg-accent-hover text-text-on-accent" in html
    assert "focus:border-border-focus" in html


def test_projects_index_keeps_grid_and_empty_state(env):
    html = render(env, "projects/index.html", _projects_ctx())
    assert "grid-cols-3" in html
    assert "Nenhum projeto ainda" not in html
    empty_ctx = _projects_ctx()
    empty_ctx["projects"] = []
    empty_ctx["issue_counts"] = {}
    html_empty = render(env, "projects/index.html", empty_ctx)
    assert "Nenhum projeto ainda" in html_empty


def test_project_detail_uses_semantic_vocabulary(env):
    html = render(env, "projects/detail.html", _project_detail_ctx())
    assert_no_legacy_vocabulary(html, "projects/detail.html")
    # Project status in a state pill; issue status badge on a neutral surface.
    assert "bg-state-on-bg text-state-on-fg" in html
    assert "bg-surface-active" in html
    assert "text-text-muted" in html
    assert "bg-surface-card border border-border-default" in html
    assert "hover:bg-surface-hover" in html
    assert "focus:border-border-focus" in html


def test_login_uses_semantic_vocabulary(env):
    html = render(env, "login.html", {})
    assert_no_legacy_vocabulary(html, "login.html")
    # Logo and primary buttons use the semantic accent; card uses surface-card.
    assert "bg-accent" in html
    assert "text-text-on-accent" in html
    assert "bg-surface-card border border-border-default" in html
    # Verification code letter spacing is preserved.
    assert "tracking-code" in html
    # Focus and inputs use semantic tokens.
    assert "focus:border-border-focus" in html
    assert "bg-surface-input border border-border-strong" in html


def test_login_preserves_two_step_forms(env):
    html = render(env, "login.html", {})
    assert 'id="email-form"' in html
    assert 'id="code-form"' in html
    assert 'type="email"' in html
    assert 'inputmode="numeric"' in html
    assert 'maxlength="6"' in html
    assert "usar outro e-mail" in html


def test_pins_sidebar_uses_design_system(env):
    html = render(env, "pins/_sidebar.html", _pins_ctx())
    assert_no_legacy_vocabulary(html, "pins/_sidebar.html")
    assert 'data-lucide="pin"' in html
    assert "text-text-faint" in html
    assert "hover:bg-surface-hover" in html
    assert "RYU-1" in html
    assert "Project one" in html
