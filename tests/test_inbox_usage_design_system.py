"""Inbox and Usage semantic design-system migration (#25)."""
from __future__ import annotations

import datetime

import pytest
from types import SimpleNamespace
from .conftest import TEMPLATES, assert_no_legacy_vocabulary, render  # noqa: F401


_COMMON_CTX = {
    "workspace": {"slug": "ws", "id": "ws-1", "name": "Workspace"},
    "user": {"name": "Dev", "email": "dev@example.com"},
}



NOW = datetime.datetime.now()


def _inbox_items():
    return [
        SimpleNamespace(id="i1", severity="action_required", title="T1", body="body1", read=False, created_at=NOW),
        SimpleNamespace(id="i2", severity="attention", title="T2", body="", read=True, created_at=NOW),
        SimpleNamespace(id="i3", severity="info", title="T3", body="", read=True, created_at=NOW),
    ]


def _inbox_ctx():
    return {
        **_COMMON_CTX,
        "active_nav": "inbox",
        "items": _inbox_items(),
        "unread": 2,
        "severity_titles": {"action_required": "Action Required", "attention": "Attention", "info": "Info"},
        "filter_read": None,
        "filter_severity": None,
    }


def _usage_ctx():
    return {
        **_COMMON_CTX,
        "active_nav": "usage",
        "summary": {
            "days": 30,
            "since": "2026-07-26T00:00:00+00:00",
            "totals": {
                "tasks": 10,
                "input_tokens": 1234567,
                "output_tokens": 89012,
                "cost_usd": 12.3456,
                "by_status": {"completed": 8, "failed": 2},
            },
            "by_agent": [
                {
                    "agent_id": "a1",
                    "agent_name": "Coder",
                    "tasks": 5,
                    "input_tokens": 1000000,
                    "output_tokens": 50000,
                    "cost_usd": 10.0,
                    "by_status": {"completed": 4, "failed": 1},
                },
                {
                    "agent_id": "a2",
                    "agent_name": "Reviewer",
                    "tasks": 5,
                    "input_tokens": 234567,
                    "output_tokens": 39012,
                    "cost_usd": 2.3456,
                    "by_status": {"completed": 4, "failed": 1},
                },
            ],
            "by_day": [
                {
                    "day": "2026-07-25",
                    "tasks": 3,
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "cost_usd": 0.0023,
                    "by_status": {"completed": 3},
                },
                {
                    "day": "2026-07-24",
                    "tasks": 7,
                    "input_tokens": 1233567,
                    "output_tokens": 88512,
                    "cost_usd": 12.3433,
                    "by_status": {"completed": 5, "failed": 2},
                },
            ],
        },
    }


@pytest.mark.parametrize("name,ctx", [
    ("inbox/index.html", _inbox_ctx()),
    ("inbox/_items.html", _inbox_ctx()),
    ("inbox/usage.html", _usage_ctx()),
])
def test_inbox_and_usage_use_semantic_vocabulary(env, name, ctx):
    assert_no_legacy_vocabulary(render(env, name, ctx), name)


def test_inbox_severity_uses_status_pill_macro(env):
    html = render(env, "inbox/_items.html", _inbox_ctx())
    assert "bg-sev-action-required-bg" in html
    assert "bg-sev-attention-bg" in html
    assert "bg-sev-info-bg" in html
    assert "Action Required" in html
    assert "Attention" in html
    assert "Info" in html
    # Severity comes from the macro, not from interpolated classes.
    assert "bg-red-500" not in html
    assert "bg-amber-400" not in html


def test_usage_keeps_number_formatting_and_alignment(env):
    html = render(env, "inbox/usage.html", _usage_ctx())
    assert "1,234,567" in html
    assert "89,012" in html
    assert "$12.3456" in html
    assert "$10.0000" in html
    assert "$2.3456" in html
    assert "$0.0023" in html
    assert "$12.3433" in html
