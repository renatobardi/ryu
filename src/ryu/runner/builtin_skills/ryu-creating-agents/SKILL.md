---
name: ryu-creating-agents
description: "Use when creating or configuring an agent: required fields, runtime/profile selection, invocation targets (who can invoke a private agent), and lifecycle (archive/restore, cancel-tasks). Traced to ryu.api.agents."
user-invocable: false
---

# Creating Agents in Ryu

Agents are created with `POST /api/agents` (`workspace_id`, `name`, `handle`
required; `runtime` defaults to the workspace's default runtime).
`_validate_agent_fields` enforces the same constraints on update: `handle`
must be a workspace-unique slug (used for `@handle` mention resolution — see
`ryu-mentioning`), and `max_concurrent_tasks` must be a positive integer if
set (it bounds how many tasks the runner claims concurrently for that
agent).

## Runtime & profile

An agent's `runtime` plus its optional `runtime_profile_id` (see
`ryu-runtimes-and-repos`) together decide which binary/protocol the runner
invokes and whether structured (`stream-json`) output parsing is used. Set
`runtime_profile_id` when you need a shared `command_name`/`fixed_args`
override instead of the raw runtime default — `_validate_profile` checks the
profile belongs to the same workspace before allowing the assignment.

## Visibility & invocation targets

A private agent (`visibility != "public"`, or with restricted
`invocation_targets`) is not invokable by every member. `PUT
/{agent_id}/invocation-targets` sets the explicit allow-list of users/agents
that may trigger it; `can_invoke_agent` (`ryu.services.agents`) is the gate
`_maybe_enqueue_agent_task` calls before letting a member-driven assignment
enqueue a task for such an agent — an unauthorized member gets 403 at
assignment time, not at task-run time.

## Lifecycle

- **archive** (`POST /{agent_id}/archive`) stops the agent from receiving new
  tasks (`archived_at` set) without deleting its history; a subsequent
  assignment attempt raises 409. **restore** clears `archived_at`.
- **cancel-tasks** (`POST /{agent_id}/cancel-tasks`) requests cancellation of
  every active (`queued`/`dispatched`/`running`) task for that agent — useful
  before archiving or when reconfiguring an agent mid-flight.
- Deleting an agent (`DELETE /{agent_id}`) is destructive; prefer archive for
  agents you may reuse.

## Skills

Attach/detach skills with `POST`/`DELETE
/api/skills/{skill_id}/agents/{agent_id}`. Every task dispatched to the agent
gets its attached workspace skills PLUS this set of platform built-in skills
(this one included) written to `skills/` in the task's work_dir — see
`ryu-skill-importing` for how to add your own.
