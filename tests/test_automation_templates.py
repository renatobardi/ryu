"""Automation templates (#26): autopilots, skills and squads use the semantic vocabulary."""
from __future__ import annotations

import pytest

from .conftest import TEMPLATES, assert_no_legacy_vocabulary, render  # noqa: F401


_COMMON = {"workspace": {"slug": "ws", "id": "ws-1", "name": "Workspace"}}


def _autopilots_ctx():
    return {
        **_COMMON,
        "autopilots": [
            {
                "id": "ap1",
                "name": "Daily sync",
                "enabled": True,
                "trigger_type": "cron",
                "cron_expr": "0 9 * * 1-5",
                "rule": "Crie uma issue de sincronização diária.",
                "webhook_token": None,
                "target_agent_id": "a1",
            },
            {
                "id": "ap2",
                "name": "Webhook receiver",
                "enabled": False,
                "trigger_type": "webhook",
                "cron_expr": None,
                "rule": None,
                "webhook_token": "tok-123",
                "target_agent_id": None,
            },
        ],
        "agents": [{"id": "a1", "name": "Coder"}],
        "agent_names": {"a1": "Coder"},
    }


def _skills_ctx():
    return {
        **_COMMON,
        "skills": [
            {
                "id": "sk1",
                "name": "Lint",
                "description": "Roda lint no código.",
                "content": "```python\nprint('ok')\n```",
            }
        ],
        "agents": [{"id": "a1", "name": "Coder"}],
        "attached": {"sk1": [{"id": "a1", "name": "Coder"}]},
    }


def _squads_ctx():
    return {
        **_COMMON,
        "squads": [
            {
                "id": "sq1",
                "name": "Core",
                "leader_agent_id": "a1",
                "description": "Squad principal",
                "instructions": "Sempre testar antes.",
            }
        ],
        "agents": [{"id": "a1", "name": "Coder"}],
        "agent_names": {"a1": "Coder"},
        "squad_members": {
            "sq1": [
                {"member_type": "agent", "member_id": "a1", "role": ""},
                {"member_type": "member", "member_id": "usr-123", "role": "ops"},
            ]
        },
        "issues": [{"id": "i1", "key": "RYU-1", "title": "Bug no board"}],
    }


@pytest.mark.parametrize(
    "name, ctx",
    [
        ("automation/autopilots.html", _autopilots_ctx()),
        ("automation/_autopilots_list.html", _autopilots_ctx()),
        ("automation/skills.html", _skills_ctx()),
        ("automation/_skills_list.html", _skills_ctx()),
        ("automation/squads.html", _squads_ctx()),
        ("automation/_squads_list.html", _squads_ctx()),
    ],
)
def test_automation_template_has_no_legacy_palette_classes(env, name, ctx):
    html = render(env, name, ctx)
    for token in ("zinc-", "violet-"):
        assert token not in html, f"{token} found in {name}"


def test_autopilot_state_uses_status_pill_macro_with_slot(env):
    html = render(env, "automation/_autopilots_list.html", _autopilots_ctx())
    assert "bg-state-on-bg text-state-on-fg" in html
    assert "bg-state-off-bg text-state-off-fg" in html
    assert "ativo" in html
    assert "pausado" in html


def test_autopilot_cron_expr_stays_monospaced(env):
    html = render(env, "automation/_autopilots_list.html", _autopilots_ctx())
    assert "0 9 * * 1-5" in html
    assert "font-mono" in html


def test_automation_forms_use_semantic_button(env):
    for name in ("automation/autopilots.html", "automation/skills.html", "automation/squads.html"):
        html = render(env, name, _autopilots_ctx() if "autopilot" in name else _skills_ctx() if "skill" in name else _squads_ctx())
        assert "bg-accent hover:bg-accent-hover text-text-on-accent" in html, f"primary button semantic classes missing in {name}"
