---
name: ryu-skill-importing
description: "Use when importing a skill from a .md/.zip file or from the runtime's local-skills directory, including conflict-resolution strategies (error/rename/overwrite/skip). Traced to ryu.api.skills import_skill/import_local_skill."
user-invocable: false
---

# Importing Skills in Ryu

`POST /api/skills/import` (multipart: `workspace_id` + `file`) accepts two
shapes:

- **`.md`** — a single Markdown file with YAML frontmatter (`name`,
  `description`). Its body (after the frontmatter) becomes the skill's
  `content`; no supporting files are attached.
- **`.zip`** — must contain exactly one top-level `SKILL.md` (frontmatter +
  body, same as above); every other file in the archive becomes a
  `SkillFile` row, with its path RELATIVE TO the `SKILL.md`'s directory
  (e.g. `my/scripts/run.py` inside the zip becomes `scripts/run.py`).

## Conflict resolution

`on_conflict` (default `"error"`) controls what happens when a skill with the
same `name` already exists in the workspace:

- **`error`** (default) — 409 with a structured conflict body; nothing is
  written.
- **`rename`** — the new skill is created as `"<name> (2)"`,
  `"<name> (3)"`, ... (first unused suffix).
- **`overwrite`** — the existing skill's `content`/`description`/files are
  replaced in place; response `status` is `"overwritten"`.
- **`skip`** — no-op; response `status` is `"skipped"`, no error raised.

## Local runtime skills

`GET /api/skills/local-runtime` scans `settings.local_skills_dir` (a
directory of `<dir_name>/SKILL.md [+ files]` bundles shipped alongside the
Ryu runtime — analogous to a built-in skills catalog you can promote into a
workspace) and lists what is available without importing anything.
`POST /api/skills/local-runtime/import` (`workspace_id`, `dir_name`, optional
`on_conflict`) imports one of those bundles the same way a `.zip` upload
would, including the same conflict-resolution options above.

## Files, labels, and path safety

Skill files are upserted by `path` (`PUT /api/skills/{id}/files`) — writing
the same path twice replaces the content rather than duplicating rows. A
path that is absolute or contains `..` is rejected with 400 at both import
time and direct file-upsert time — a skill can never write outside its own
directory when the runner later materializes it into a task's `skills/`
tree (`ryu.runner.loop`). Labels (`/api/skills/{id}/labels`) are a plain
tagging mechanism usable as a `label_id` filter on `GET /api/skills`.
