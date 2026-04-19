"""MCP server exposing Gauntlet's deterministic primitives.

Gauntlet runs exclusively inside a Claude Code session. The host agent plays
the Attacker and Inspector roles (two prompt contexts it drives itself) and
calls this MCP server for the deterministic pieces: config loading, plan
execution against the SUT, and risk-report assembly.

The train/test split is a host-side prompt discipline:

- ``list_weapons`` returns ``WeaponBrief`` objects with no ``blockers``. Safe
  to read in the host's Attacker context.
- ``get_weapon`` returns the full ``Weapon`` including ``blockers``. The host
  must only read this in its HoldoutEvaluator context, never in its Attacker
  context.
- ``execute_plan`` is surface-agnostic: it runs both attacker probes and
  holdout acceptance plans the same way.
- ``build_risk_report`` assembles the final ``RiskReport`` and ``Clearance``
  from iteration records the host has accumulated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

from .adapters import HttpApi
from .auth import UsersConfig, to_user_headers
from .executor import Drone
from .loop import build_default_iteration_specs, build_risk_report
from .models import (
    Arsenal,
    Clearance,
    ExecutionResult,
    IterationRecord,
    IterationSpec,
    Plan,
    RiskReport,
    Target,
    Weapon,
    WeaponAssessment,
    WeaponBrief,
)
from .openapi import parse_openapi
from .roles import DemoWeaponAssessor

mcp = FastMCP("gauntlet")

_DEFAULT_WEAPONS_PATH = ".gauntlet/weapons"
_DEFAULT_TARGETS_PATH = ".gauntlet/targets"
_DEFAULT_USERS_PATH = ".gauntlet/users.yaml"


def _load_weapons_from_dir(path: Path) -> list[Weapon]:
    return [Weapon(**yaml.safe_load(f.read_text())) for f in sorted(path.glob("*.yaml"))]


def _load_weapons(weapons_path: str, arsenal_path: str | None) -> list[Weapon]:
    if arsenal_path:
        data = yaml.safe_load(Path(arsenal_path).read_text())
        return Arsenal(**data).weapons
    path = Path(weapons_path)
    if not path.exists():
        return []
    if path.is_dir():
        return _load_weapons_from_dir(path)
    return [Weapon(**yaml.safe_load(path.read_text()))]


def _load_targets(targets_path: str, openapi_path: str | None) -> list[Target]:
    targets: list[Target] = []
    path = Path(targets_path)
    if path.exists():
        if path.is_dir():
            targets = [Target(**yaml.safe_load(f.read_text())) for f in sorted(path.glob("*.yaml"))]
        else:
            targets = [Target(**yaml.safe_load(path.read_text()))]
    if openapi_path:
        targets = parse_openapi(openapi_path) + targets
    return targets


def _load_user_headers(users_path: str) -> dict[str, dict[str, str]]:
    path = Path(users_path)
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text())
    return to_user_headers(UsersConfig(**data))


@mcp.tool()
def list_weapons(
    weapons_path: str = _DEFAULT_WEAPONS_PATH,
    arsenal_path: str | None = None,
) -> list[WeaponBrief]:
    """Return attacker-safe views of available weapons.

    ``blockers`` are intentionally omitted. Call this in the host's Attacker
    context to pick a weapon to probe.
    """
    return [w.brief() for w in _load_weapons(weapons_path, arsenal_path)]


@mcp.tool()
def get_weapon(
    weapon_id: str,
    weapons_path: str = _DEFAULT_WEAPONS_PATH,
    arsenal_path: str | None = None,
) -> Weapon:
    """Return the full weapon, including ``blockers``.

    HOST DISCIPLINE: only call this in a HoldoutEvaluator context. Never read
    the result in an Attacker context — doing so collapses the train/test
    split and invalidates the run.
    """
    for weapon in _load_weapons(weapons_path, arsenal_path):
        if weapon.id == weapon_id or weapon.title == weapon_id:
            return weapon
    raise ValueError(f"No weapon with id or title {weapon_id!r}")


@mcp.tool()
def list_targets(
    targets_path: str = _DEFAULT_TARGETS_PATH,
    openapi_path: str | None = None,
) -> list[Target]:
    """Return available target API surfaces.

    Targets from ``openapi_path`` (if given) are prepended to any written
    targets in ``targets_path``.
    """
    return _load_targets(targets_path, openapi_path)


@mcp.tool()
def execute_plan(
    url: str,
    plan: Plan,
    users_path: str = _DEFAULT_USERS_PATH,
) -> ExecutionResult:
    """Execute a plan against a live HTTP API and return the result.

    ``url`` is the base URL of the SUT. ``users_path`` is an optional YAML
    file resolving user names to credentials (see auth.py); if omitted or
    missing, the Drone sends an ``X-User: <name>`` header fallback.
    """
    user_headers = _load_user_headers(users_path)
    drone = Drone(HttpApi(url, user_headers=user_headers))
    return drone.run_plan(plan)


@mcp.tool()
def assess_weapon(
    weapon_id: str,
    weapons_path: str = _DEFAULT_WEAPONS_PATH,
    arsenal_path: str | None = None,
    target: Target | None = None,
) -> WeaponAssessment:
    """Preflight quality check on a weapon.

    Reads the full weapon (including blockers) internally but only returns
    a ``WeaponAssessment`` — the blocker text itself is never surfaced.
    """
    for weapon in _load_weapons(weapons_path, arsenal_path):
        if weapon.id == weapon_id or weapon.title == weapon_id:
            return DemoWeaponAssessor().assess(weapon, target)
    raise ValueError(f"No weapon with id or title {weapon_id!r}")


@mcp.tool()
def assemble_run_report(
    iterations: list[IterationRecord],
    holdout_results: list[ExecutionResult] | None = None,
    clearance_threshold: float = 0.90,
) -> dict[str, Any]:
    """Assemble the final ``RiskReport`` and ``Clearance`` from iteration records.

    The host passes the ``IterationRecord`` list it has accumulated across
    attacker/inspector turns, plus any holdout ``ExecutionResult`` objects
    from running the weapon's acceptance plans. Returns the report plus a
    clearance recommendation (``pass``, ``conditional``, or ``block``).
    """
    report, clearance = build_risk_report(iterations, holdout_results or [], clearance_threshold)
    return {
        "risk_report": report.model_dump(),
        "clearance": clearance.model_dump() if clearance else None,
    }


@mcp.tool()
def default_iteration_specs() -> list[IterationSpec]:
    """Return the default 4-stage iteration ladder as reference.

    baseline → boundary → adversarial_misuse → targeted_escalation. The host
    may follow this ladder or author its own spec list.
    """
    return build_default_iteration_specs()


__all__ = [
    "Clearance",
    "RiskReport",
    "assemble_run_report",
    "assess_weapon",
    "default_iteration_specs",
    "execute_plan",
    "get_weapon",
    "list_targets",
    "list_weapons",
    "mcp",
    "main",
]


def main() -> None:
    """Run the MCP server over stdio (the Claude Code transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
