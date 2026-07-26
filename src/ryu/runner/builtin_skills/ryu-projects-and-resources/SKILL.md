---
name: ryu-projects-and-resources
description: "Use when reasoning about how Projects group issues, project status, and workspace-level resources (agents, squads, skills, runtime profiles) an issue's work can draw on. Traced to ryu.api.projects and related workspace-scoped APIs."
user-invocable: false
---

# Projects & Resources in Ryu

## Projects

A `Project` (`/api/projects`, workspace-scoped) is a lightweight grouping for
issues: `POST /api/projects` creates one (`workspace_id`, `name`, optional
`status`/description fields); `GET /api/projects/{id}/issues` lists the
issues currently linked to it. Moving an issue's `project_id` (via
`PATCH /api/issues` or the batch-update endpoint) is logged as an activity
entry (`payload["project_id"] = {"from": ..., "to": ...}`) but does NOT by
itself trigger any agent dispatch — only `status`/`assignee` changes do that
(see `ryu-working-on-issues`). Use projects to scope reporting/filtering, not
as an automation trigger.

## Workspace-level resources an issue can draw on

When working an issue, the resources available in its workspace are:

- **Agents** (`/api/agents`) — see `ryu-creating-agents` for how they're
  configured and invoked.
- **Squads** (`/api/squads`) — see `ryu-squads` for the leader-briefing model.
- **Skills** (`/api/skills`) — attached per-agent, materialized into every
  task's `skills/` directory alongside this platform skill set; see
  `ryu-skill-importing` for how to add more.
- **Runtime profiles** (`/api/runtime-profiles`) — shared command/protocol
  overrides; see `ryu-runtimes-and-repos`.
- **Autopilots** (`/api/autopilots`) — scheduled/webhook/manual dispatch into
  this workspace's agents; see `ryu-autopilots`.

All of the above are scoped by `workspace_id` — a resource created in one
workspace is never visible to, or invokable from, another workspace's issues,
even if the same user is a member of both.
