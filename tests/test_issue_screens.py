"""Design-system migration for issue screens (#23)."""
from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "src/ryu/web/templates"


@pytest.fixture(scope="module")
def env():
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )


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

_NOW = datetime.datetime.now()


def _render(env, name, ctx):
    return env.get_template(name).render(**ctx)


def _board_ctx():
    cols = {st: [] for st in _STATUS_TITLES}
    cols["backlog"] = [
        {
            "id": "i1",
            "key": "RYU-1",
            "title": "Urgent agent issue",
            "priority": "urgent",
            "assignee_type": "agent",
            "assignee_id": "a1",
        },
        {
            "id": "i2",
            "key": "RYU-2",
            "title": "Low member issue",
            "priority": "low",
            "assignee_type": "member",
            "assignee_id": "u1",
        },
    ]
    cols["todo"] = [
        {
            "id": "i3",
            "key": "RYU-3",
            "title": "No priority",
            "priority": "none",
            "assignee_type": None,
            "assignee_id": None,
        },
    ]
    return {
        **_COMMON_CTX,
        "active_nav": "board",
        "column_order": list(_STATUS_TITLES.keys()),
        "status_titles": _STATUS_TITLES,
        "columns": cols,
        "agents": [{"id": "a1", "name": "Coder", "handle": "coder"}],
        "agent_names": {"a1": "Coder"},
    }


def _detail_ctx():
    return {
        **_COMMON_CTX,
        "active_nav": "board",
        "issue": {
            "id": "issue-1",
            "key": "RYU-10",
            "title": "Detail issue",
            "description": "Some description",
            "status": "in_progress",
            "priority": "high",
            "assignee_type": "agent",
            "assignee_id": "a1",
            "created_at": _NOW,
            "updated_at": _NOW,
        },
        "labels": [{"name": "bug", "color": "var(--status-blocked)"}],
        "comments": [],
        "attachments": [],
        "sub_issues": [
            {"key": "RYU-11", "title": "Done sub", "status": "done"},
            {"key": "RYU-12", "title": "Todo sub", "status": "todo"},
        ],
        "activity": [
            {"action": "created", "actor_type": "member", "created_at": _NOW}
        ],
        "agents": [{"id": "a1", "name": "Coder", "handle": "coder"}],
        "agent_names": {"a1": "Coder"},
        "statuses": list(_STATUS_TITLES.keys()),
        "priorities": ["urgent", "high", "medium", "low", "none"],
        "status_titles": _STATUS_TITLES,
    }


def _comments_ctx():
    return {
        **_COMMON_CTX,
        "issue": {"id": "issue-1", "key": "RYU-10"},
        "comments": [
            {
                "id": "c1",
                "author_type": "agent",
                "author_id": "a1",
                "body": "agent comment",
                "created_at": _NOW,
                "resolved_at": None,
                "parent_comment_id": None,
            },
            {
                "id": "c2",
                "author_type": "member",
                "author_id": "u1",
                "body": "member comment",
                "created_at": _NOW,
                "resolved_at": None,
                "parent_comment_id": None,
            },
            {
                "id": "c3",
                "author_type": "system",
                "author_id": None,
                "body": "system comment",
                "created_at": _NOW,
                "resolved_at": _NOW,
                "parent_comment_id": None,
            },
        ],
    }


def _attachments_ctx():
    return {
        **_COMMON_CTX,
        "issue": {"id": "issue-1", "key": "RYU-10"},
        "attachments": [
            {
                "id": "att-1",
                "filename": "notes.txt",
                "download_url": "/api/attachments/att-1/download",
                "size_bytes": 2048,
            }
        ],
    }


def _assert_no_legacy_tokens(html, source):
    for token in ("zinc-", "violet-", "#111116"):
        assert token not in html, f"{token} found in {source}"


# ── Board columns ───────────────────────────────────────────────────────────


def test_board_columns_use_semantic_vocabulary(env):
    html = _render(env, "issues/_board_columns.html", _board_ctx())
    _assert_no_legacy_tokens(html, "_board_columns.html")
    # priority drawn by explicit semantic token map, not arbitrary colors
    assert "bg-prio-urgent-bg" in html
    assert "text-prio-urgent-fg" in html
    assert "bg-prio-low-bg" in html
    assert "text-prio-low-fg" in html
    assert "bg-red-500/15" not in html
    assert "bg-zinc-700/40" not in html


def test_board_columns_use_lucide_for_assignee(env):
    html = _render(env, "issues/_board_columns.html", _board_ctx())
    assert 'data-lucide="bot"' in html
    assert 'data-lucide="user"' in html


def test_board_columns_drag_and_drop_attributes(env):
    html = _render(env, "issues/_board_columns.html", _board_ctx())
    assert 'draggable="true"' in html
    assert 'data-column-status="backlog"' in html
    assert 'data-issue-id="i1"' in html


# ── Board page ──────────────────────────────────────────────────────────────


def test_board_page_uses_semantic_vocabulary(env):
    html = _render(env, "issues/board.html", _board_ctx())
    _assert_no_legacy_tokens(html, "board.html")
    assert "bg-accent" in html
    assert "border-border-default" in html


# ── Detail page ─────────────────────────────────────────────────────────────


def test_detail_page_uses_semantic_vocabulary(env):
    html = _render(env, "issues/detail.html", _detail_ctx())
    _assert_no_legacy_tokens(html, "detail.html")
    # sub-issue status uses the status_dot macro, not a zinc badge
    assert "bg-status-done" in html
    assert "bg-status-todo" in html
    assert "bg-zinc-800 text-zinc-400" not in html


def test_detail_page_uses_lucide_for_assignee(env):
    html = _render(env, "issues/detail.html", _detail_ctx())
    assert 'data-lucide="bot"' in html


# ── Comments ────────────────────────────────────────────────────────────────


def test_comments_preserve_author_markers_and_use_lucide(env):
    html = _render(env, "issues/_comments.html", _comments_ctx())
    _assert_no_legacy_tokens(html, "_comments.html")
    # author markers preserved as emoji text
    assert "🤖" in html
    assert "👤" in html
    # resolved badge uses Lucide instead of emoji checkmark
    assert 'data-lucide="check"' in html
    # author markers stay as emoji, not Lucide icons
    assert 'data-lucide="bot"' not in html
    assert 'data-lucide="user"' not in html


# ── Attachments ─────────────────────────────────────────────────────────────


def test_attachments_use_lucide(env):
    html = _render(env, "issues/_attachments.html", _attachments_ctx())
    _assert_no_legacy_tokens(html, "_attachments.html")
    assert 'data-lucide="paperclip"' in html
    assert "📎" not in html
