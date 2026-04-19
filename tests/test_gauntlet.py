from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gauntlet import (
    Assertion,
    HttpRequest,
    IterationRecord,
    IterationSpec,
    Plan,
    PlanStep,
    build_risk_report,
)
from gauntlet.server import get_weapon, list_weapons

from ._factories import make_execution_result

# ---------------------------------------------------------------------------
# Shared authorization probe used to anchor model shapes across tests.
# ---------------------------------------------------------------------------

_AUTHZ_PLAN = Plan(
    name="user_cannot_modify_other_users_task",
    category="authz",
    goal="cross-user modification should be rejected",
    steps=[
        PlanStep(
            user="userA",
            request=HttpRequest(method="POST", path="/tasks", body={"title": "private task"}),
        ),
        PlanStep(
            user="userB",
            request=HttpRequest(method="PATCH", path="/tasks/{task_id}", body={"completed": True}),
        ),
    ],
    assertions=[
        Assertion(
            name="unauthorized_patch_blocked",
            expected=403,
            step_index=2,
        ),
    ],
)


def _spec(name: str = "baseline") -> IterationSpec:
    return IterationSpec(
        index=1,
        name=name,
        goal=name,
        attacker_prompt="",
        inspector_prompt="",
    )


# ---------------------------------------------------------------------------
# Risk-report assembly
# ---------------------------------------------------------------------------


def test_build_risk_report_reflects_holdout_failure() -> None:
    """With zero-satisfaction holdout results and no findings, clearance blocks."""
    execution = make_execution_result(passing=False)
    iteration = IterationRecord(
        spec=_spec(),
        plans=[_AUTHZ_PLAN],
        execution_results=[execution],
        findings=[],
    )

    report, clearance = build_risk_report([iteration], [execution], clearance_threshold=0.9)

    assert clearance is not None
    assert clearance.passed is False
    assert clearance.recommendation == "block"
    assert report.risk_level == "low"  # no findings means no blocker-level severity


def test_build_risk_report_no_holdout_yields_no_clearance() -> None:
    iteration = IterationRecord(
        spec=_spec(),
        plans=[],
        execution_results=[],
        findings=[],
    )
    _, clearance = build_risk_report([iteration], [], clearance_threshold=0.9)
    assert clearance is None


# ---------------------------------------------------------------------------
# MCP tool surface
# ---------------------------------------------------------------------------


@pytest.fixture
def weapons_dir(tmp_path: Path) -> Path:
    d = tmp_path / "weapons"
    d.mkdir()
    (d / "ownership.yaml").write_text(
        yaml.dump(
            {
                "id": "resource_ownership_write_isolation",
                "title": "Users cannot modify each other's tasks",
                "description": "The task API must enforce resource ownership.",
                "blockers": ["A PATCH by a non-owner is rejected with 403"],
            }
        )
    )
    return d


def test_list_weapons_omits_blockers(weapons_dir: Path) -> None:
    briefs = list_weapons(weapons_path=str(weapons_dir))
    assert len(briefs) == 1
    brief = briefs[0]
    assert brief.id == "resource_ownership_write_isolation"
    assert brief.title == "Users cannot modify each other's tasks"
    # WeaponBrief has no blockers field — Pydantic enforces this, but belt-and-braces:
    assert not hasattr(brief, "blockers")


def test_get_weapon_returns_full_weapon(weapons_dir: Path) -> None:
    weapon = get_weapon(
        weapon_id="resource_ownership_write_isolation",
        weapons_path=str(weapons_dir),
    )
    assert weapon.blockers == ["A PATCH by a non-owner is rejected with 403"]


def test_get_weapon_raises_on_unknown_id(weapons_dir: Path) -> None:
    with pytest.raises(ValueError, match="No weapon"):
        get_weapon(weapon_id="nonexistent", weapons_path=str(weapons_dir))


def test_get_weapon_lookup_is_id_only(weapons_dir: Path) -> None:
    """Lookup is id-only; the human-readable title is no longer accepted."""
    with pytest.raises(ValueError, match="No weapon"):
        get_weapon(
            weapon_id="Users cannot modify each other's tasks",
            weapons_path=str(weapons_dir),
        )
