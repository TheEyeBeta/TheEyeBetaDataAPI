---
name: personal-ci
description: >
  Run before opening or updating a PR in TheEyeBetaDataAPI. Local, focused
  "personal CI" for the files actually changed — do not treat GitHub Actions as
  the first test run. Adapted from TheEyeProd AGENTS.md "Personal CI" pattern;
  DataAPI-specific commands only (pytest / ruff / pip-audit). Not for trading
  or OMS work.
---

# Personal CI — TheEyeBetaDataAPI

Before opening or updating a PR, run a local focused check for the actual files
changed. This is compulsory; do not use GitHub Actions as the first test run.

## Minimum expectations

| Change type | Local check |
|---|---|
| Python (`app/`, `tests/`, `scripts/*.py`) | `ruff check .` + `ruff format --check .` + `mypy` + narrowest meaningful `pytest` set; broaden to full `pytest` when auth/shared behavior is touched |
| `requirements*.txt` | `pip-audit -r requirements-dev.txt` + full `pytest` |
| `deploy/*.sql`, `app/auth/`, IAM repositories | `TEST_POSTGRES_URL=<scratch superuser URL> pytest tests/integration -q` (throwaway server only) |
| SQL in `app/repositories/`, `contracts/prod/` | Prod contract suite: `PROD_CONTRACT=1` + env from the `prod-contract` job in `ci.yml`, `pytest tests/contract -q` |
| Routes / scopes / env / scripts / CI | Also run the `readme-sync` skill obligations |
| Docs-only | `git diff --check` + read the sections you edited |
| Deploy/systemd/scripts | Confirm `--user` systemd commands match `AGENTS.md` (never invent `sudo systemctl` for this unit) |

## Commands

```bash
# From repo root, with venv active (pip install -r requirements-dev.txt; CI uses Python 3.12)
ruff check . && ruff format --check . && mypy
pytest tests/test_<area>.py -q
pytest -q                         # before claiming the branch is ready
pip-audit -r requirements-dev.txt # when dependencies change
gitleaks git --config .gitleaks.toml .  # if gitleaks is installed (CI job `secrets`)
```

If a check cannot run locally (e.g. no host Postgres for a live SQL apply), run
what can run, state the blocker explicitly in the PR/report, and watch CI. A
skipped local check is not a silent pass.

## Do not import from Prod

- Do not run Prod `make test` / `tb` / investment-operating-model gates here.
- Do not treat green CI alone as "deployed" — DataAPI deploy is proven by the
  self-hosted `deploy` job (`/health` with `"database": true`, then
  `scripts/e2e_admin_smoke.py`; see `scripts/deploy.sh`).
