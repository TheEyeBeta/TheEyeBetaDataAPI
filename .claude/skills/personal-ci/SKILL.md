---
name: personal-ci
description: >
  Run before opening or updating a PR in TheEyeBetaDataAPI. Local, focused
  "personal CI" for the files actually changed — do not treat GitHub Actions as
  the first test run. Adapted from TheEyeProd AGENTS.md "Personal CI" pattern;
  DataAPI-specific commands only (pytest / ruff if available). Not for trading
  or OMS work.
---

# Personal CI — TheEyeBetaDataAPI

Before opening or updating a PR, run a local focused check for the actual files
changed. This is compulsory; do not use GitHub Actions as the first test run.

## Minimum expectations

| Change type | Local check |
|---|---|
| Python (`app/`, `tests/`, `scripts/*.py`) | Narrowest meaningful `pytest` set; broaden to full `pytest` when auth/shared behavior is touched |
| Routes / scopes / env / scripts / CI | Also run the `readme-sync` skill obligations |
| Docs-only | `git diff --check` + read the sections you edited |
| Deploy/systemd/scripts | Confirm `--user` systemd commands match `AGENTS.md` (never invent `sudo systemctl` for this unit) |

## Commands

```bash
# From repo root, with venv active (CI uses Python 3.11; local 3.12 is fine)
pytest tests/test_<area>.py -q
pytest -q   # before claiming the branch is ready
```

If a check cannot run locally (e.g. no host Postgres for a live SQL apply), run
what can run, state the blocker explicitly in the PR/report, and watch CI. A
skipped local check is not a silent pass.

## Do not import from Prod

- Do not run Prod `make test` / `tb` / investment-operating-model gates here.
- Do not treat green CI alone as "deployed" — DataAPI deploy is proven by the
  self-hosted `deploy` job + `/health` (see `scripts/deploy.sh`).
