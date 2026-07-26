---
name: ryu-squads
description: "Use when reasoning about squad-assigned issues: who gets briefed, how the leader's no_action suppresses further comments this round, and how a worker or an @handle mention can wake the leader. Traced to ryu.services.automation (squad_briefing_on_assign, handle_comment_squad_triggers, should_suppress_leader_comment)."
user-invocable: false
---

# Squads in Ryu

A `Squad` has a `leader_agent_id` and a roster of `member`/`agent` rows
(`ryu.models.Squad`, `/api/squads`). Assigning an issue to a squad (instead of
a single agent) routes work through the leader rather than dispatching every
member directly.

## Assignment briefs the leader, not the whole squad

When `issue.assignee_type == "squad"`, `_maybe_enqueue_agent_task` delegates
to `automation_svc.squad_briefing_on_assign`, which creates the `AgentTask`
for the squad's `leader_agent_id` (same dedup rule as a direct agent
assignment: no second task while one is queued/dispatched/running). The same
function fires on both the initial assignment and a `backlog → todo`
promotion — assigning early and promoting later both brief the leader
exactly once each time it's warranted.

## What re-wakes the leader after that

`handle_comment_squad_triggers` runs (best-effort) after every comment on the
issue and re-briefs the leader when either:

- the issue is still assigned to that squad, or
- the comment body contains the squad's `@handle` (its name, lower-cased).

The leader authoring its own comment does **not** re-trigger itself — that
guard (`_should_suppress_squad_leader_self_trigger`) exists specifically to
avoid a self-feeding loop. A worker on the SAME squad commenting, a human, or
an unrelated agent all DO re-brief the leader — that's the intended way for a
worker to hand a result back up.

## `no_action` suppresses the leader's own next comment

If the leader records a `squad_evaluated` activity-log entry for the current
round and does not follow up with a new task, `should_suppress_leader_comment`
rejects (409) any further comment attempt by that same leader on that issue —
the round is considered closed until new work arrives. This keeps a leader
that decided "nothing to do this round" from posting noise anyway.

## Practical guidance

- Assign squad work to the squad, not to the leader agent directly, so the
  leader gets the standard brief-and-dedup handling.
- As a worker, comment normally when you finish a sub-task — it will surface
  to the leader through the trigger path above.
- As a leader, if you log `no_action`, expect your own next comment attempt
  on that issue to be rejected until a new task exists — don't retry blindly.
