"""Filter pg_dump output into a portable contract snapshot (stdin -> stdout).

Drops what is Prod behaviour rather than shape, or needs Prod-only objects:
foreign keys, triggers, row-level security, session SET lines, and any
statement that references TimescaleDB internals. Also drops psql
meta-commands (pg_dump >= 16.10 emits `\restrict <random token>`), which keeps
the output loadable by any client and byte-for-byte reproducible.
"""

from __future__ import annotations

import re
import sys

text = sys.stdin.read()
statements = re.split(r"(?<=;)\n", text)
kept: list[str] = []
for statement in statements:
    body = "\n".join(line for line in statement.splitlines() if not line.startswith(("--", "\\"))).strip()
    if not body:
        continue
    upper = body.upper()
    if body.startswith(("SET ", "SELECT pg_catalog.set_config")):
        continue
    if "FOREIGN KEY" in upper or upper.startswith("CREATE TRIGGER") or "ROW LEVEL SECURITY" in upper:
        continue
    if upper.startswith(("CREATE POLICY", "CREATE SCHEMA", "ALTER SCHEMA", "COMMENT ON")):
        continue
    if "_TIMESCALEDB" in upper or "TIMESCALEDB_" in upper:
        continue
    kept.append(body)
sys.stdout.write("\n\n".join(kept) + "\n")
