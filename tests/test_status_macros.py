"""Status macros (#20): status_dot for issue status, status_pill coverage.

Seam: render the macros via a Jinja2 Environment pointed at the templates
directory and assert the emitted HTML. The macros are pure class-string
emitters — the risk the ticket calls out (interpolation producing a
non-existent class silently) is a static property of the source.
"""
from __future__ import annotations

import pytest

from .conftest import TEMPLATES


COMPONENTS = TEMPLATES / "_components"


def render(env, src):
    """Renderiza um snippet inline — aqui os macros são exercitados isolados."""
    return env.from_string(src).render()


# CONTRACTS.md rule 9 — issue status enum.
ISSUE_STATUSES = ["backlog", "todo", "in_progress", "in_review", "done", "blocked", "cancelled"]
# CONTRACTS.md rule 9 — task status enum.
TASK_STATUSES = ["queued", "dispatched", "running", "completed", "failed", "cancelled"]
# Agent, severity and state enums (from StatusPill.d.ts / CONTRACTS.md).
AGENT_STATUSES = ["idle", "working", "blocked", "error", "offline"]
SEVERITY_STATUSES = ["action_required", "attention", "info"]
STATE_STATUSES = ["on", "off"]




# ── status_dot ──────────────────────────────────────────────────────────────


def test_status_dot_macro_exists():
    assert (COMPONENTS / "data" / "status_dot.html").exists()


@pytest.mark.parametrize("status", ISSUE_STATUSES)
def test_status_dot_resolves_every_issue_status_to_real_class(env, status):
    html = render(
        env,
        '{% from "_components/data/status_dot.html" import status_dot %}'
        f'{{{{ status_dot(status="{status}") }}}}',
    )
    # The token name is hyphenated; the enum value is underscored. The macro
    # must map explicitly, never interpolate bg-status-{{ status }}.
    expected_token = status.replace("_", "-")
    assert f"bg-status-{expected_token}" in html, f"status_dot({status=}) missing bg-status-{expected_token}"


def test_status_dot_default_label_is_raw_status_visible(env):
    # Without a caller, the raw backend value renders as the visible
    # default label beside the dot (AC #4: "rótulo padrão é o valor cru
    # do backend, minúsculo"). The dot also carries aria-label for AT.
    html = render(
        env,
        '{% from "_components/data/status_dot.html" import status_dot %}'
        '{{ status_dot(status="in_progress") }}',
    )
    assert "in_progress" in html
    assert 'aria-label="in_progress"' in html
    # No title tooltip — StatusDot.jsx only has aria-label.
    assert 'title="' not in html


def test_status_dot_call_slot_overrides_default_label(env):
    # With a caller, the slot content overrides the raw default label —
    # the override for when the raw value isn't presentable.
    html = render(
        env,
        '{% from "_components/data/status_dot.html" import status_dot %}'
        '{% call status_dot(status="done") %}Done{% endcall %}',
    )
    assert "Done" in html
    assert "bg-status-done" in html
    # The dot is decorative when a visible label sibling exists — no
    # aria-label (would make AT announce the status twice).
    assert "aria-label" not in html
    assert 'aria-hidden="true"' in html


def test_status_dot_has_no_inline_style():
    src = (COMPONENTS / "data" / "status_dot.html").read_text()
    # CONTRACTS.md rule 7 + USAGE.md: never inline style.
    assert "style=" not in src


def test_status_dot_source_has_no_class_interpolation():
    src = (COMPONENTS / "data" / "status_dot.html").read_text()
    # The forbidden pattern: building a class name by interpolating the raw
    # backend value (which is underscored) into a hyphenated token namespace.
    assert "bg-status-{{" not in src
    assert "bg-status-{%" not in src


# ── status_pill ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", TASK_STATUSES)
def test_status_pill_task_resolves_every_task_status(env, status):
    html = render(
        env,
        '{% from "_components/data/status_pill.html" import status_pill %}'
        f'{{{{ status_pill(kind="task", status="{status}") }}}}',
    )
    expected_token = status.replace("_", "-")
    assert f"bg-task-{expected_token}-bg" in html, f"task {status} missing bg-task-{expected_token}-bg"


@pytest.mark.parametrize("status", AGENT_STATUSES)
def test_status_pill_agent_resolves_every_agent_status(env, status):
    html = render(
        env,
        '{% from "_components/data/status_pill.html" import status_pill %}'
        f'{{{{ status_pill(kind="agent", status="{status}") }}}}',
    )
    assert f"bg-agent-{status}-bg" in html, f"agent {status} missing class"


@pytest.mark.parametrize("status", SEVERITY_STATUSES)
def test_status_pill_severity_resolves_every_severity(env, status):
    html = render(
        env,
        '{% from "_components/data/status_pill.html" import status_pill %}'
        f'{{{{ status_pill(kind="severity", status="{status}") }}}}',
    )
    expected_token = status.replace("_", "-")
    assert f"bg-sev-{expected_token}-bg" in html, f"severity {status} missing class"


@pytest.mark.parametrize("status", STATE_STATUSES)
def test_status_pill_state_resolves_every_state(env, status):
    html = render(
        env,
        '{% from "_components/data/status_pill.html" import status_pill %}'
        f'{{{{ status_pill(kind="state", status="{status}") }}}}',
    )
    assert f"bg-state-{status}-bg" in html, f"state {status} missing class"


def test_status_pill_default_label_is_raw_status_lowercase(env):
    html = render(
        env,
        '{% from "_components/data/status_pill.html" import status_pill %}'
        '{{ status_pill(kind="task", status="running") }}',
    )
    assert "running" in html


def test_status_pill_call_slot_overrides_label(env):
    html = render(
        env,
        '{% from "_components/data/status_pill.html" import status_pill %}'
        '{% call status_pill(kind="state", status="on") %}ativo{% endcall %}',
    )
    assert "ativo" in html


def test_status_pill_source_has_no_class_interpolation():
    src = (COMPONENTS / "data" / "status_pill.html").read_text()
    assert "bg-task-{{" not in src
    assert "bg-agent-{{" not in src
    assert "bg-sev-{{" not in src
    assert "bg-state-{{" not in src
