---
name: ryu-mentioning
description: "Use when a comment or issue description needs to @mention an agent or a member. Documents Ryu's actual mention contract: @handle resolution (agent by handle, member by email localpart or name), auto-subscription, and which mentions can wake a squad leader. Traced to ryu.services.issues.resolve_mentions and ryu.services.automation.handle_comment_squad_triggers."
user-invocable: false
---

# Mentioning in Ryu

This skill documents WHAT an `@handle` does in Ryu, traced to source. It is
narrower than it may sound: Ryu's mention grammar is plain `@handle` text, not
a `mention://type/id` link.

## The mention grammar

`resolve_mentions()` (`ryu.services.issues`) extracts handles with
`MENTION_RE` (a simple `@word` regex) from free text, lower-cases them, and
resolves each against two tables in the issue's workspace:

- **Agents** — matched by `agent.handle` (with a leading `@` stripped).
- **Members** — matched by the local part of `user.email` (before the `@`)
  OR by `user.name`, case-insensitively.

There is no UUID link syntax to build — you write `@apbot` or `@alice` in the
comment/description body and the resolver looks the handle up by name at
write time. If two entities share a handle, both are added to the resolved
list; if nothing matches, the mention is silently dropped (no error).

## What a mention actually does

1. **Auto-subscription only, by default.** `_auto_subscribe_mentions()` calls
   `subscribe(db, issue.id, user_type, user_id, "mentioned")` for every
   resolved handle. This adds the mentioned agent/member to the issue's
   subscriber list (reason `mentioned`) and to the notification fan-out via
   `_notify_subscribers`. It does **not** by itself enqueue an `AgentTask` —
   mentioning `@apbot` in a comment does not make `apbot` run.
2. **`@squad-handle` can wake the squad leader.** Comment creation always
   calls `automation_svc.handle_comment_squad_triggers(db, issue, author_type,
   author_id, body)` (best-effort — a failure there never blocks the
   comment). That function scans the comment body for `@<squad-handle>` (the
   squad's name lower-cased into a handle) in addition to the case where the
   issue's `assignee_type == "squad"`, and enqueues a briefing task for that
   squad's leader — unless the leader itself authored the comment (no
   self-trigger).
3. **Assignee auto-trigger is separate from mentions.** An agent gets a
   queued `AgentTask` when it becomes the issue's `assignee` and the issue is
   `todo`/`in_progress` (`_maybe_enqueue_agent_task`), not from being
   `@mentioned` in a comment. Do not expect `@agent-handle` alone to dispatch
   that agent — assign the issue to it instead, or mention the owning squad's
   handle if you want the squad leader briefed.

## Practical guidance

- To notify a person or agent without running anything, `@mention` them —
  it only subscribes them to updates.
- To wake a squad's leader from a comment, use the squad's handle (its name,
  lower-cased, matching how `_squad_handle()` derives it in
  `ryu.services.automation`), or assign the issue to that squad.
- To make a specific agent actually work, assign the issue to it (or use
  `/api/agents/{id}/invocation-targets` + the autopilots/manual-run path) —
  mentioning alone is not a dispatch mechanism in Ryu.
