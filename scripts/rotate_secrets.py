#!/usr/bin/env python3
"""Rotate local runtime secrets in .env with a verify overlap window.

Rotates:
- JWT_SECRET / JWT_SIGNING_SECRET_CURRENT (new signing secret)
- JWT_SIGNING_SECRET_PREVIOUS (previous signing secret, verify-only)
- USER_JWT_SECRET / USER_JWT_SECRET_PREVIOUS
- SERVICE_CLIENTS_JSON[*].secret

See docs/SECRET_ROTATION_RUNBOOK.md. After restart, wait one full max token TTL
before clearing *_PREVIOUS (this script leaves PREVIOUS set on purpose).
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
from pathlib import Path

from dotenv import dotenv_values


def _new_secret() -> str:
    return secrets.token_urlsafe(36)


def main() -> int:
    env_path = Path(".env")
    if not env_path.exists():
        print("No .env file found in current directory.")
        return 1

    raw_values = dotenv_values(env_path)
    values = {key: value for key, value in raw_values.items() if value is not None}

    old_signing = (
        values.get("JWT_SIGNING_SECRET_CURRENT")
        or values.get("JWT_SECRET")
        or ""
    )
    new_signing = _new_secret()
    if old_signing:
        values["JWT_SIGNING_SECRET_PREVIOUS"] = old_signing
    values["JWT_SIGNING_SECRET_CURRENT"] = new_signing
    values["JWT_SECRET"] = new_signing

    old_user = values.get("USER_JWT_SECRET") or ""
    new_user = _new_secret()
    if old_user:
        values["USER_JWT_SECRET_PREVIOUS"] = old_user
    values["USER_JWT_SECRET"] = new_user

    clients_raw = values.get("SERVICE_CLIENTS_JSON", "{}")
    try:
        clients = json.loads(clients_raw)
    except json.JSONDecodeError:
        print("SERVICE_CLIENTS_JSON is not valid JSON; aborting rotation.")
        return 1
    if not isinstance(clients, dict):
        print("SERVICE_CLIENTS_JSON is not an object; aborting rotation.")
        return 1

    rotated_client_secrets: dict[str, str] = {}
    for client_id, config in clients.items():
        if not isinstance(config, dict):
            continue
        secret = _new_secret()
        config["secret"] = secret
        rotated_client_secrets[str(client_id)] = secret

    values["SERVICE_CLIENTS_JSON"] = json.dumps(clients, separators=(",", ":"))

    backup_path = env_path.with_name(
        f"{env_path.name}.bak.{dt.datetime.now(dt.UTC).strftime('%Y%m%d%H%M%S')}"
    )
    backup_path.write_text(env_path.read_text(encoding="utf-8"), encoding="utf-8")
    backup_path.chmod(0o600)

    existing_lines = env_path.read_text(encoding="utf-8").splitlines()
    rewritten: list[str] = []
    updated_keys: set[str] = set()

    for line in existing_lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            rewritten.append(line)
            continue
        key, _, _ = line.partition("=")
        if key in values:
            rewritten.append(f"{key}={values[key]}")
            updated_keys.add(key)
        else:
            rewritten.append(line)

    for key in (
        "JWT_SECRET",
        "JWT_SIGNING_SECRET_CURRENT",
        "JWT_SIGNING_SECRET_PREVIOUS",
        "USER_JWT_SECRET",
        "USER_JWT_SECRET_PREVIOUS",
        "SERVICE_CLIENTS_JSON",
    ):
        if key in values and key not in updated_keys:
            rewritten.append(f"{key}={values[key]}")

    env_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    env_path.chmod(0o600)

    print(f"Rotated secrets written to {env_path} (mode 600). Backup saved at {backup_path} (mode 600).")
    print("JWT signing CURRENT rotated; PREVIOUS retained for verify overlap.")
    print("After restart, wait >= SERVICE_TOKEN_EXPIRES_MINUTES, then clear *_PREVIOUS.")
    print("See docs/SECRET_ROTATION_RUNBOOK.md.")
    print("Updated service client secrets:")
    for client_id, secret in rotated_client_secrets.items():
        print(f"  {client_id}: {secret}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
