---
name: ryu-working-on-issues
description: "Use when an agent needs to understand how it receives work, what happens on assignment/status change, how comments and subscribers/notifications flow, and how a run resumes an existing session. Traced to ryu.services.issues and ryu.runner.loop."
user-invocable: false
---

# Working on Issues in Ryu

## How you get dispatched

An `AgentTask` is created for you when an issue you are assigned to enters
`todo` or `in_progress` (`_maybe_enqueue_agent_task` in
`ryu.services.issues`). The prompt is `title` plus `description` (when
present). If you are already `queued`/`dispatched`/`running` on that issue,
no duplicate task is created. An archived agent cannot receive a new task
(409). A squad-assigned issue instead briefs the squad leader — see the
`ryu-squads` skill.

## Workdir, prompt, skills

Each task's runner sets up a fresh `work_dir` with `PROMPT.md` (the task
prompt), `AGENT.md` (your persisted instructions, if any), and a `skills/`
tree — one directory per skill attached to you, each holding a `SKILL.md`
plus any supporting files, indexed in `SKILLS.md`. This bundle (including
this skill) is written by `ryu.runner.loop` before your runtime process is
launched.

## Resuming a session

If a later task targets the same issue/chat, the runner reuses the existing
`work_dir` and passes `--resume <session_id>` to a `claude`-protocol runtime,
so you keep prior context instead of starting cold. Do not assume a fresh
task on the same issue means a fresh conversation — check `AGENT.md` /
`PROMPT.md` history in the workdir if unsure.

## Comments, mentions, subscribers

Post progress via the comments API. Every comment:

- Auto-subscribes its author (reason `commenter`) and any `@mentioned`
  handles (reason `mentioned`) — see the `ryu-mentioning` skill for exactly
  how `@handle` resolves and what it does NOT do (it does not by itself
  dispatch another agent).
- Best-effort triggers `handle_comment_squad_triggers`, so commenting on a
  squad-assigned issue (or using the squad's `@handle`) can wake that squad's
  leader — unless the leader itself is the author (no self-trigger loop).
- Fans out to subscribers' inbox (`_notify_subscribers`), gated by their
  notification preferences for the `comments` group.
- If the assigning squad leader already logged a `no_action` for this round
  (`squad_evaluated` activity log entry with no follow-up task since), your
  comment as that leader is rejected with 409 — this stops a leader from
  chattering into an issue it decided needs no further work this round.

## Status changes

Moving an issue's `status` or `assignee` re-runs the same auto-trigger check
(`_maybe_enqueue_agent_task`), so promoting an issue from `backlog` to `todo`
can dispatch a task exactly like a direct assignment would. Batch updates
(`batch_update_issues`) apply the same rule per-issue.
