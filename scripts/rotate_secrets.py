#!/usr/bin/env python3
"""Rotate local runtime secrets in .env.

Rotates:
- JWT_SECRET
- USER_JWT_SECRET
- SERVICE_CLIENTS_JSON[*].secret
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

    values["JWT_SECRET"] = _new_secret()
    values["USER_JWT_SECRET"] = _new_secret()

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

    backup_path = env_path.with_name(f"{env_path.name}.bak.{dt.datetime.now(dt.UTC).strftime('%Y%m%d%H%M%S')}")
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

    for key in ("JWT_SECRET", "USER_JWT_SECRET", "SERVICE_CLIENTS_JSON"):
        if key not in updated_keys:
            rewritten.append(f"{key}={values[key]}")

    env_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    env_path.chmod(0o600)

    print(f"Rotated secrets written to {env_path} (mode 600). Backup saved at {backup_path} (mode 600).")
    print("Updated service client secrets:")
    for client_id, secret in rotated_client_secrets.items():
        print(f"  {client_id}: {secret}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
