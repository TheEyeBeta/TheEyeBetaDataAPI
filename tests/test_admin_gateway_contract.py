"""The /admin/* gateway manifest matches what TheEyeBetaProd admin-service serves.

contracts/prod/admin_route_families.json is generated from admin-service at
contracts/prod/PROD_SHA (scripts/prod_contract_admin_routes.py). These tests
fail if the gateway exposes a method Prod does not implement, keeps a family
Prod removed, or misses a route Prod added without a recorded decision.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.routes.admin_gateway import ADMIN_ROUTE_MANIFEST

CONTRACT_DIR = Path(__file__).resolve().parents[1] / "contracts" / "prod"
CONTRACT = json.loads((CONTRACT_DIR / "admin_route_families.json").read_text(encoding="utf-8"))

# Prod methods the gateway deliberately does not expose. Each needs a reason.
DELIBERATELY_BLOCKED_METHODS: dict[str, set[str]] = {
    # Operator creation stays off the public gateway; the terminal only lists users.
    "users": {"POST"},
}
# Prod admin-service routes outside every gateway family, with the reason.
DELIBERATELY_UNCOVERED: dict[tuple[str, str], str] = {
    ("GET", "health"): "admin-service liveness is probed on the host, not via the public gateway",
    ("GET", "dataapi/{param}"): "admin-service's own DataAPI proxy; exposing it would loop DataAPI -> admin -> DataAPI",
}


def _family(rule_prefix: str) -> str:
    return rule_prefix.strip("/")


def test_contract_matches_pinned_prod_sha() -> None:
    pinned = (CONTRACT_DIR / "PROD_SHA").read_text(encoding="utf-8").strip()
    assert CONTRACT["prod_sha"] == pinned


def test_manifest_families_are_exactly_the_contract_families() -> None:
    assert {_family(rule.prefix) for rule in ADMIN_ROUTE_MANIFEST} == set(CONTRACT["families"])


@pytest.mark.parametrize("rule", ADMIN_ROUTE_MANIFEST, ids=lambda rule: rule.prefix)
def test_manifest_methods_match_prod_minus_deliberate_blocks(rule) -> None:
    family = _family(rule.prefix)
    prod_methods = set(CONTRACT["families"][family])
    assert prod_methods, f"{family}: Prod admin-service has no route here; remove it from the manifest"
    assert set(rule.methods) <= prod_methods, f"{family}: gateway allows methods Prod does not implement"
    missing = prod_methods - set(rule.methods)
    assert missing == DELIBERATELY_BLOCKED_METHODS.get(family, set()), (
        f"{family}: Prod implements {sorted(missing)} that the gateway does not expose; "
        "add it to the manifest or record the decision in DELIBERATELY_BLOCKED_METHODS"
    )


def test_prod_routes_outside_the_manifest_are_deliberate() -> None:
    uncovered = {tuple(item) for item in CONTRACT["uncovered"]}
    assert uncovered == set(DELIBERATELY_UNCOVERED)
