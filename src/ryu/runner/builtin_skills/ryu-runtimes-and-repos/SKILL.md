---
name: ryu-runtimes-and-repos
description: "Use when reasoning about which CLI/protocol runs a task, how a runtime_profile overrides the binary/args, and how a task's repo_url is cloned into the workdir. Traced to ryu.runner.adapters.build_command/runtime_env and ryu.runner.loop."
user-invocable: false
---

# Runtimes & Repos in Ryu

## Protocol families

Ryu supports these runtime protocol families (`PROTOCOL_FAMILIES` in
`ryu.runner.adapters`): `claude`, `codex`, `gemini`, `opencode`, `copilot`,
`cursor-agent`, `qwen`. An agent's `runtime` field (or its
`runtime_profile.protocol_family`, when a profile is attached) selects which
family's argv-building branch in `build_command()` is used. If the resolved
binary is not found on PATH/filesystem, `build_command` returns `None` and
the task falls back to Ryu's deterministic stub executor instead of
crashing — a missing CLI is not a hard failure, it's a soft, testable no-op.

## Runtime profiles

A `RuntimeProfile` (`/api/runtime-profiles`, workspace-scoped) lets a team
share one `command_name` + `fixed_args` override across agents instead of
repeating raw runtime config per agent — e.g. pinning a specific wrapper
script, or a fixed set of extra flags appended after the family's own args.
Only the `claude` family gets structured output (`--output-format
stream-json --verbose`) and thus per-event `TaskMessage` transcription; other
families run in plain text mode. `resume_session_id` is honored for
`claude` (`--resume <id>`) so a follow-up task on the same issue/chat
continues the prior session — `codex`'s resume is currently a documented
no-op (falls through silently rather than erroring).

## Model & thinking/service-tier

`runtime_env()` derives environment variables from the agent's
`thinking_level` and `service_tier` fields; `model` on the agent (or an env
override) is passed as `--model`/`-m` per family. Check `agent_env_overrides`
in `ryu.runner.adapters` before assuming a family's default binary/model —
workspace-level env overrides take precedence.

## Repos

If a task's dispatch `config` carries a `repo_url` and the task's `work_dir`
does not already have a `repo/` subdirectory, the runner does a shallow
(`--depth 1`) `git clone` into `workdir/repo` before launching the runtime
process (`ryu.runner.loop`). This only happens once per work_dir — a resumed
session on the same issue reuses the already-cloned checkout rather than
re-cloning.
