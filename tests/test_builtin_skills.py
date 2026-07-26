"""Testes do ciclo 2 de paridade — skills built-in de plataforma.

Multica sempre acrescenta um conjunto fixo de skills de plataforma
(mentioning/autopilots/squads/etc.) por cima das skills de workspace do
agente (task.go:3777 LoadAgentSkillBundles + builtin_skills.go). Este teste
cobre o equivalente Ryu: ryu.runner.builtin_skills.load_builtin_skills() e a
materialização em skills/<slug>/SKILL.md pelo runner (loop.py)."""
from __future__ import annotations

from pathlib import Path

from tests.conftest import login

EXPECTED_SLUGS = {
    "ryu-mentioning",
    "ryu-autopilots",
    "ryu-working-on-issues",
    "ryu-squads",
    "ryu-creating-agents",
    "ryu-runtimes-and-repos",
    "ryu-skill-importing",
    "ryu-projects-and-resources",
}


def test_load_builtin_skills_returns_all_platform_skills():
    from ryu.runner.builtin_skills import load_builtin_skills

    skills = load_builtin_skills()
    slugs = {s.slug for s in skills}
    assert slugs == EXPECTED_SLUGS
    for s in skills:
        assert s.content.startswith("---\n"), s.slug  # frontmatter presente
        assert f"name: {s.slug}" in s.content, s.slug


async def test_dispatched_task_receives_builtin_skills_in_workdir(client):
    from ryu.runner.loop import _run_one

    data = await login(client, "builtin-skills-owner@example.com")
    ws_id = data["workspaces"][0]["id"]
    r = await client.post("/api/agents", json={"workspace_id": ws_id, "name": "Bot", "handle": "bskbot"})
    assert r.status_code in (200, 201), r.text
    agent_id = r.json()["id"]

    r = await client.post(
        "/api/issues",
        json={"workspace_id": ws_id, "title": "tarefa", "status": "todo",
              "assignee_type": "agent", "assignee_id": agent_id},
    )
    assert r.status_code == 201, r.text
    issue = r.json()

    r = await client.get(f"/api/tasks/issues/{issue['id']}/active")
    task = r.json()["task"]
    assert task is not None

    await _run_one(task["id"])

    r = await client.get(f"/api/tasks/{task['id']}")
    workdir = Path(r.json()["work_dir"])
    skills_root = workdir / "skills"
    for slug in EXPECTED_SLUGS:
        skill_md = skills_root / slug / "SKILL.md"
        assert skill_md.is_file(), f"faltando {skill_md}"
        assert skill_md.read_text(encoding="utf-8").strip()

    index = (workdir / "SKILLS.md").read_text(encoding="utf-8")
    for slug in EXPECTED_SLUGS:
        assert slug in index
