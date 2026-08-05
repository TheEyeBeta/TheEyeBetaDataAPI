---
name: readme-sync
description: >
  ACTIVATE THIS SKILL whenever a change in this repo adds, removes, or changes the
  behavior of: an API route or query/body parameter, an auth scope, an environment
  variable read by app/core/config.py, a script under scripts/, a systemd service or
  how it's installed/restarted/deployed, or a GitHub Actions workflow job. Triggers on
  edits to app/api/routes/*.py, app/auth/scopes.py, app/core/config.py, .env.example,
  scripts/*.sh, scripts/*.py, .github/workflows/*.yml, or any *.service unit. Also
  activate before closing out any task that touches those files, even if README
  updates weren't explicitly requested — treat doc drift as part of the change, not a
  follow-up. Use this skill in Claude Code, Cursor, Codex, and any other agent working
  this repo — it is not specific to one tool.
---

# README / API reference sync — TheEyeBetaDataAPI

This repo keeps two human-facing docs that describe runtime behavior, and they drift
independently of the code if nobody updates them on purpose:

- **`README.md`** — architecture, auth model, scope list, the route-group summary
  table, setup/deploy/service-management commands.
- **`docs/API_REFERENCE.md`** — the detailed per-endpoint reference (params,
  response shape, curl examples) that `README.md` explicitly delegates to.

A code change that adds a route, param, or scope but skips these docs isn't done —
it's shipped confusion for the next person (human or agent) who reads the docs
instead of the diff.

## What actually happened without this discipline

`scripts/deploy.sh`, `scripts/install_service.sh`, and `README.md`'s "Service
management" section all independently assumed `theeyebeta-dataapi` was a
system-level systemd unit (`sudo systemctl ...`). The actual deployed unit is a
`--user` one. Nobody had update this convention consistently across all three
places, and the deploy job in CI had been silently failing to restart the real
service for over a month before anyone actually checked. This is the failure
mode this skill exists to prevent — not hypothetical.

## When you touch code, also touch docs

| If you changed... | Update... |
|---|---|
| A route, its params, or its response shape (`app/api/routes/*.py`, `app/schemas/*.py`) | `docs/API_REFERENCE.md` (the endpoint's section — add one if new) **and** `README.md`'s route-group summary table |
| A scope constant (`app/auth/scopes.py`) | `README.md`'s scope list **and** `docs/API_REFERENCE.md`'s `## Scopes` table |
| An env var read by `app/core/config.py` | `.env.example` (with a safe placeholder, never a real value) **and** the relevant `README.md` section |
| A script under `scripts/` (setup, deploy, rotate, install) | The `README.md` section that documents running it — keep the exact commands in the doc byte-for-byte runnable |
| How the service is installed, restarted, or deployed (`*.service` unit, `scripts/deploy.sh`, `scripts/install_service.sh`, `.github/workflows/*.yml`) | `README.md`'s "Production setup" and "Service management" sections — and double check the systemd scope (`--user` vs system) actually matches what the unit file says, don't assume |
| A GitHub Actions job (new workflow, new required runner label, new secret) | `README.md`'s CI/CD-relevant setup section |

## Verification before you call it done

1. Grep the docs for the thing you changed — if a route/scope/env var name you
   touched doesn't appear in `README.md` or `docs/API_REFERENCE.md` and should,
   it's not done.
2. If you documented a shell command, run it (or the read-only parts of it) to
   confirm it's not stale — this repo has a documented-but-wrong `sudo systemctl`
   command that survived multiple PRs because nobody actually ran it.
3. Keep `AGENTS.md` in sync too if the change is the kind of non-obvious
   operational gotcha a fresh agent session would need (not just any change —
   see `AGENTS.md` itself for what belongs there vs. what belongs in `README.md`).
