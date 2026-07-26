---
name: ryu-autopilots
description: "Use when configuring or reasoning about an Autopilot: what each trigger_type does (manual/schedule/api/webhook/event), how execution_mode (default vs run_only) changes whether an issue is created, and how webhook delivery lifecycle (dedupe, signing, replay, rotation) behaves. Traced to ryu.api.autopilots and ryu.services.automation."
user-invocable: false
---

# Autopilots in Ryu

Autopilots are workspace automations that dispatch a `target_agent_id` when a
trigger fires, tracked in the `Autopilot` / `AutopilotTrigger` /
`AutopilotRun` tables (`ryu.models`), exposed at `/api/autopilots`.

## Trigger types

- **manual** — fired via `POST /api/autopilots/{id}/run`, optionally with a
  `trigger_id` pointing at a specific `api`-kind trigger (the run's `source`
  reflects that).
- **schedule** — a trigger row with `kind="schedule"`, a required
  `cron_expression`, and an optional IANA `timezone` (validated at creation;
  an invalid cron or timezone is rejected with 400).
- **api** — a trigger with `kind="api"`; runs are started by naming its id in
  the manual-run call.
- **webhook** — a trigger with a `webhook_token`; deliveries land at
  `POST /api/autopilots/hook/{token}`, are persisted, and may be filtered by
  `event_filters` (a list of `{event, actions}` matched against
  `X-GitHub-Event`/payload `action`).

## execution_mode

- **default** — a run creates (or reuses, per `issue_title_template`) an
  `Issue` and assigns it to `target_agent_id`, so the normal
  assignee-auto-trigger path enqueues the `AgentTask`.
- **run_only** — no `Issue` is created; the run's `AgentTask` is dispatched
  directly with the rule text as the prompt. Use this for autopilots that
  should not clutter the issue board (e.g. a housekeeping bot).

## Webhook delivery lifecycle

Every delivery is durably recorded (`AutopilotDelivery`) with an `outcome` —
`dispatched`, `duplicate`, `rejected`, or `ignored` — before/while the run is
attempted, so nothing is lost even if the target is paused:

- **Dedup** — an `Idempotency-Key` header matching a prior delivery bumps
  `attempt_count` and returns `status: "duplicate"` with the SAME
  `delivery_id`; it never creates a second run.
- **Signing** — once a trigger has a `signing_secret` (set via
  `PUT .../triggers/{id}/signing-secret`), every delivery must carry a valid
  `X-Hub-Signature-256: sha256=<hmac>` header or it is `rejected` with reason
  `missing_signature` / `invalid_signature` (401). Clearing the secret
  (`signing_secret: ""`) turns verification back off.
- **event_filters** — a delivery whose `X-GitHub-Event`/action does not match
  any configured filter is accepted at the HTTP layer but recorded as
  `ignored` with reason `event_filtered`; nothing is dispatched.
- **paused / archived autopilot** — deliveries are `ignored` with reason
  `autopilot_paused` / `autopilot_archived`; `archived` also rejects manual
  `/run` with 409.
- **Replay** — `POST .../deliveries/{id}/replay` re-derives a fresh delivery
  and run from a past payload, stamping
  `replayed_from_delivery_id`.
- **Token rotation** — `POST .../triggers/{id}/rotate-webhook-token`
  invalidates the old token immediately (subsequent hits return 404).

## Rule versions, collaborators, subscribers

Every substantive change to `rule` (or other config fields) appends an
`AutopilotVersion` row, and a run records the `rule_version_id` that was
current when it fired — so you can trace which rule text produced a given
run. `collaborators` gate mutation/manual-run beyond the owner (403 for
outsiders); `subscribers` are auto-added to any issue the autopilot creates
(reason `autopilot`) so they see the resulting activity in their inbox.
