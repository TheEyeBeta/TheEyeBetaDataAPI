"""The production deploy job must depend on every other CI job."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def test_deploy_needs_every_check() -> None:
    jobs = _jobs()
    checks = set(jobs) - {"deploy"}
    assert set(jobs["deploy"]["needs"]) == checks


def test_deploy_only_from_main_push_and_never_concurrently() -> None:
    deploy = _jobs()["deploy"]
    assert deploy["if"] == "github.ref == 'refs/heads/main' && github.event_name == 'push'"
    assert deploy["concurrency"]["cancel-in-progress"] is False


def test_deploy_pins_the_tested_commit() -> None:
    steps = {step.get("name"): step for step in _jobs()["deploy"]["steps"]}
    assert steps["Deploy to production"]["env"]["DEPLOY_SHA"] == "${{ github.sha }}"


def test_no_check_is_allowed_to_fail() -> None:
    for name, job in _jobs().items():
        assert not job.get("continue-on-error"), name
        for step in job.get("steps", []):
            assert not step.get("continue-on-error"), f"{name}: {step.get('name')}"
