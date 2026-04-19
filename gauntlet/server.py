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
from .loop import aggregate_final_clearance, build_default_iteration_specs, build_risk_report
from .models import (
    Arsenal,
    Clearance,
    ExecutionResult,
    FinalClearance,
    HoldoutResult,
    IterationRecord,
    IterationSpec,
    Plan,
    RiskReport,
    Target,
    Weapon,
    WeaponAssessment,
    WeaponBrief,
    WeaponReport,
)
from .openapi import parse_openapi
from .roles import DemoWeaponAssessor
from .runs import DEFAULT_RUNS_PATH, RunStore

mcp = FastMCP("gauntlet")

_DEFAULT_WEAPONS_PATH = ".gauntlet/weapons"
_DEFAULT_TARGETS_PATH = ".gauntlet/targets"
_DEFAULT_USERS_PATH = ".gauntlet/users.yaml"

_run_store = RunStore(DEFAULT_RUNS_PATH)


def _store(runs_path: str | None) -> RunStore:
    """Return the shared store, or a per-call store if a custom path is given."""
    if runs_path is None or runs_path == DEFAULT_RUNS_PATH:
        return _run_store
    return RunStore(runs_path)


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
    iterations: list[IterationRecord] | None = None,
    holdout_results: list[ExecutionResult] | None = None,
    clearance_threshold: float = 0.90,
    run_id: str | None = None,
    weapon_id: str | None = None,
    runs_path: str | None = None,
) -> dict[str, Any]:
    """Assemble the final ``RiskReport`` and ``Clearance`` for one weapon.

    Two calling shapes are supported:

    - **Run-buffer mode** (preferred): pass ``run_id`` and ``weapon_id``. The
      server reads the iteration and holdout buffers it owns and assembles
      the report. The host does not manage filesystem layout for run state.
    - **Explicit mode** (legacy): pass ``iterations`` and ``holdout_results``
      directly. Useful for hosts that have not yet adopted ``start_run`` /
      ``record_iteration`` / ``record_holdout_result``.

    Returns the report plus a clearance recommendation (``pass``,
    ``conditional``, or ``block``).
    """
    if run_id is not None and weapon_id is not None:
        store = _store(runs_path)
        records = store.read_iteration_records(run_id, weapon_id)
        holdouts = [hr.execution_result for hr in store.read_holdout_results(run_id, weapon_id)]
    elif iterations is not None:
        records = iterations
        holdouts = list(holdout_results or [])
    else:
        raise ValueError("assemble_run_report requires either (run_id, weapon_id) or 'iterations'.")

    report, clearance = build_risk_report(records, holdouts, clearance_threshold)
    return {
        "risk_report": report.model_dump(),
        "clearance": clearance.model_dump() if clearance else None,
    }


@mcp.tool()
def start_run(weapon_ids: list[str], runs_path: str | None = None) -> dict[str, str]:
    """Initialize a new run-scoped buffer and return the opaque ``run_id``.

    Carry the returned ``run_id`` through subsequent ``record_iteration``,
    ``read_iteration_records``, ``record_holdout_result``,
    ``read_holdout_results``, and ``assemble_run_report`` calls. The buffer
    is short-lived: one run, one host session.
    """
    return {"run_id": _store(runs_path).start_run(weapon_ids)}


@mcp.tool()
def record_iteration(
    run_id: str,
    weapon_id: str,
    iteration_record: IterationRecord,
    runs_path: str | None = None,
) -> dict[str, str]:
    """Append one ``IterationRecord`` to the weapon's per-run buffer.

    Called by the Attacker (after composing plans + executing them) and by
    the Inspector (after analysing ``ExecutionResult``s into ``Finding``s).
    Findings must have ``violated_blocker=None`` — the Inspector never sees
    blocker text, and the train/test split forbids it from entering this
    buffer.
    """
    _store(runs_path).record_iteration(run_id, weapon_id, iteration_record)
    return {"status": "ok"}


@mcp.tool()
def read_iteration_records(
    run_id: str, weapon_id: str, runs_path: str | None = None
) -> list[IterationRecord]:
    """Return every ``IterationRecord`` previously appended for this weapon.

    Called by the Attacker (to read its own prior plans + Inspector findings)
    and by the Inspector (to read prior findings). Both reads are train/test
    safe: nothing returned here ever contains blocker text.
    """
    return _store(runs_path).read_iteration_records(run_id, weapon_id)


@mcp.tool()
def record_holdout_result(
    run_id: str,
    weapon_id: str,
    holdout_result: HoldoutResult,
    runs_path: str | None = None,
) -> dict[str, str]:
    """Append one ``HoldoutResult`` to the weapon's holdout buffer.

    Called only by the HoldoutEvaluator after executing one acceptance plan
    derived from a weapon's blocker. ``HoldoutResult.weapon_id`` must match
    the ``weapon_id`` argument.
    """
    _store(runs_path).record_holdout_result(run_id, weapon_id, holdout_result)
    return {"status": "ok"}


@mcp.tool()
def read_holdout_results(
    run_id: str, weapon_id: str, runs_path: str | None = None
) -> list[HoldoutResult]:
    """Return every ``HoldoutResult`` previously appended for this weapon.

    Called by the Orchestrator when assembling reports. Must NOT be called
    from the Attacker or Inspector role — holdout outcomes carry blocker
    semantics and reading them collapses the train/test split.
    """
    return _store(runs_path).read_holdout_results(run_id, weapon_id)


@mcp.tool()
def assemble_final_clearance(
    run_id: str,
    clearance_threshold: float = 0.90,
    weapon_ids: list[str] | None = None,
    runs_path: str | None = None,
) -> FinalClearance:
    """Aggregate every per-weapon report in a run into one overall clearance.

    Reads the run buffer for every weapon declared at ``start_run`` time
    (override with ``weapon_ids`` if you only want a subset), assembles a
    per-weapon ``RiskReport`` + ``Clearance`` for each, and reduces them to
    a single ``FinalClearance``.

    Aggregation rules (see :class:`FinalClearance`):

    - ``overall_confidence`` = min over per-weapon confidence_score and
      holdout_satisfaction_score (weakest link dominates).
    - ``max_risk_level`` = max severity across per-weapon risk levels.
    - ``final_recommendation`` = ``pass`` only when threshold is met AND no
      medium- or high-risk weapons; ``conditional`` when threshold is met
      with medium-risk weapons but no high-risk; ``block`` otherwise.

    Allow this tool only in the Orchestrator role. Attacker and Inspector
    contexts must not see per-weapon reports — they carry confirmed-failure
    text that paraphrases blocker semantics.
    """
    store = _store(runs_path)
    weapons = list(weapon_ids) if weapon_ids is not None else store.list_weapon_ids(run_id)

    per_weapon: list[WeaponReport] = []
    for wid in weapons:
        records = store.read_iteration_records(run_id, wid)
        holdouts = [hr.execution_result for hr in store.read_holdout_results(run_id, wid)]
        report, clearance = build_risk_report(records, holdouts, clearance_threshold)
        per_weapon.append(WeaponReport(weapon_id=wid, risk_report=report, clearance=clearance))

    return aggregate_final_clearance(per_weapon, clearance_threshold)


@mcp.tool()
def default_iteration_specs() -> list[IterationSpec]:
    """Return the default 4-stage iteration ladder as reference.

    baseline → boundary → adversarial_misuse → targeted_escalation. The host
    may follow this ladder or author its own spec list.
    """
    return build_default_iteration_specs()


__all__ = [
    "Clearance",
    "FinalClearance",
    "RiskReport",
    "assemble_final_clearance",
    "assemble_run_report",
    "assess_weapon",
    "default_iteration_specs",
    "execute_plan",
    "get_weapon",
    "list_targets",
    "list_weapons",
    "main",
    "mcp",
    "read_holdout_results",
    "read_iteration_records",
    "record_holdout_result",
    "record_iteration",
    "start_run",
]


def main() -> None:
    """Run the MCP server over stdio (the Claude Code transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
