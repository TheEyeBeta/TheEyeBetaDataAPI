#!/usr/bin/env python3
"""Create a local .env file with required runtime settings.

This utility starts from .env.example, generates strong local secrets,
and requires a concrete DATABASE_URL so the app can actually start.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import sys
from pathlib import Path


def _new_secret() -> str:
    return secrets.token_urlsafe(36)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap local .env from .env.example")
    parser.add_argument(
        "--template",
        default=".env.example",
        help="Path to template env file (default: .env.example)",
    )
    parser.add_argument(
        "--output",
        default=".env",
        help="Path to output env file (default: .env)",
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="Database URL override. If omitted, reads DATABASE_URL from shell env.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output file if it already exists (creates timestamped backup).",
    )
    parser.add_argument(
        "--trust-proxy-headers",
        action="store_true",
        help="Set TRUST_PROXY_HEADERS=true (use when running behind trusted proxy/tunnel).",
    )
    return parser.parse_args()


def _parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        normalized_key = key.strip()
        if not normalized_key:
            continue
        values[normalized_key] = value.strip()
    return values


def _load_template_values(template_text: str) -> dict[str, str]:
    return _parse_env_text(template_text)


def _resolve_database_url(cli_value: str, template_values: dict[str, str]) -> str:
    candidates = [cli_value.strip(), os.getenv("DATABASE_URL", "").strip(), template_values.get("DATABASE_URL", "").strip()]
    for candidate in candidates:
        if candidate and "REPLACE_ME" not in candidate:
            return candidate
    raise ValueError(
        "DATABASE_URL is required. Pass --database-url or export DATABASE_URL before running this script."
    )


def _resolve_service_clients(raw_value: str) -> tuple[str, list[str]]:
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError("SERVICE_CLIENTS_JSON in template is invalid JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("SERVICE_CLIENTS_JSON in template must be a JSON object")

    client_ids: list[str] = []
    for client_id, config in parsed.items():
        if not isinstance(config, dict):
            continue
        config["secret"] = _new_secret()
        client_ids.append(str(client_id))

    compact = json.dumps(parsed, separators=(",", ":"))
    return compact, client_ids


def _render_env(template_text: str, values: dict[str, str]) -> str:
    updated_keys: set[str] = set()
    rendered: list[str] = []
    for line in template_text.splitlines():
        stripped = line.lstrip()
        if not line or stripped.startswith("#") or "=" not in line:
            rendered.append(line)
            continue
        key, _, _ = line.partition("=")
        normalized_key = key.strip()
        if normalized_key in values:
            rendered.append(f"{normalized_key}={values[normalized_key]}")
            updated_keys.add(normalized_key)
        else:
            rendered.append(line)

    for key, value in values.items():
        if key not in updated_keys:
            rendered.append(f"{key}={value}")
    return "\n".join(rendered).rstrip() + "\n"


def main() -> int:
    args = _parse_args()

    template_path = Path(args.template)
    output_path = Path(args.output)
    if not template_path.exists():
        print(f"Template file not found: {template_path}", file=sys.stderr)
        return 1

    if output_path.exists():
        if not args.force:
            print(f"Refusing to overwrite existing file: {output_path}. Use --force to replace it.", file=sys.stderr)
            return 1
        backup = output_path.with_name(
            f"{output_path.name}.bak.{dt.datetime.now(dt.UTC).strftime('%Y%m%d%H%M%S')}"
        )
        backup.write_text(output_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backed up existing {output_path} to {backup}")

    template_text = template_path.read_text(encoding="utf-8")
    values = _load_template_values(template_text)

    try:
        values["DATABASE_URL"] = _resolve_database_url(args.database_url, values)
        values["JWT_SECRET"] = _new_secret()
        values["USER_JWT_SECRET"] = _new_secret()
        service_clients_json, client_ids = _resolve_service_clients(values.get("SERVICE_CLIENTS_JSON", "{}"))
        values["SERVICE_CLIENTS_JSON"] = service_clients_json
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    # Local-safe default: do not trust forwarded headers unless requested.
    values["TRUST_PROXY_HEADERS"] = "true" if args.trust_proxy_headers else "false"
    values.setdefault("API_HOST", "127.0.0.1")
    values.setdefault("API_PORT", "7000")

    rendered = _render_env(template_text, values)
    output_path.write_text(rendered, encoding="utf-8")

    client_list = ", ".join(client_ids) if client_ids else "(none)"
    print(f"Wrote {output_path} with generated local secrets.")
    print(f"Configured service clients: {client_list}")
    print("Next: run `bash scripts/run_local.sh`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
