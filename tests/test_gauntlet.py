from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gauntlet import (
    Assertion,
    DemoWeaponAssessor,
    Drone,
    HttpRequest,
    InMemoryHttpApi,
    IterationRecord,
    IterationSpec,
    Plan,
    PlanStep,
    Target,
    Weapon,
    build_default_iteration_specs,
    build_risk_report,
)
from gauntlet.server import (
    assemble_run_report,
    assess_weapon,
    default_iteration_specs,
    get_weapon,
    list_targets,
    list_weapons,
)

# ---------------------------------------------------------------------------
# Shared authorization probe reused across several tests.
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
        PlanStep(user="userA", request=HttpRequest(method="GET", path="/tasks/{task_id}")),
    ],
    assertions=[
        Assertion(
            name="unauthorized_patch_blocked",
            kind="status_code",
            expected=403,
            step_index=2,
        ),
        Assertion(
            name="task_not_modified_by_other_user",
            kind="rule",
            rule="task_not_modified_by_other_user",
            step_index=3,
        ),
    ],
)


# ---------------------------------------------------------------------------
# Drone and assertion evaluation (unchanged deterministic core)
# ---------------------------------------------------------------------------


def test_drone_executes_authz_plan_and_surfaces_flaw() -> None:
    result = Drone(InMemoryHttpApi()).run_plan(_AUTHZ_PLAN)

    assert result.steps[1].response.status_code == 200  # seeded flaw
    assert result.assertions[0].passed is False
    assert result.assertions[1].passed is False
    assert result.satisfaction_score == 0.0


# ---------------------------------------------------------------------------
# Risk-report assembly
# ---------------------------------------------------------------------------


def test_build_risk_report_reflects_holdout_failure() -> None:
    """With zero-satisfaction holdout results and no findings, clearance blocks."""
    execution = Drone(InMemoryHttpApi()).run_plan(_AUTHZ_PLAN)
    iteration = IterationRecord(
        spec=build_default_iteration_specs()[0],
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
        spec=build_default_iteration_specs()[0],
        plans=[],
        execution_results=[],
        findings=[],
    )
    _, clearance = build_risk_report([iteration], [], clearance_threshold=0.9)
    assert clearance is None


# ---------------------------------------------------------------------------
# Weapon quality assessment
# ---------------------------------------------------------------------------


def test_weapon_assessor_rejects_vague_weapon() -> None:
    vague = Weapon(
        title="Make it secure",
        description="It should be secure.",
        blockers=["secure", "no bugs"],
    )
    assessment = DemoWeaponAssessor().assess(vague, None)
    assert assessment.proceed is False
    assert assessment.quality_score < 0.5


def test_weapon_assessor_accepts_good_weapon() -> None:
    good = Weapon(
        title="Users cannot modify each other's tasks",
        description="The task API must enforce resource ownership.",
        blockers=["A PATCH by a non-owner is rejected with 403"],
    )
    target = Target(title="Task endpoints", endpoints=["PATCH /tasks/{id}"])
    assessment = DemoWeaponAssessor().assess(good, target)
    assert assessment.proceed is True
    assert assessment.quality_score >= 0.5


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


def test_list_targets_reads_yaml_dir(tmp_path: Path) -> None:
    targets_dir = tmp_path / "targets"
    targets_dir.mkdir()
    (targets_dir / "task_endpoints.yaml").write_text(
        yaml.dump(
            {
                "title": "Task endpoints",
                "endpoints": ["POST /tasks", "PATCH /tasks/{id}"],
            }
        )
    )
    targets = list_targets(targets_path=str(targets_dir))
    assert len(targets) == 1
    assert targets[0].endpoints == ["POST /tasks", "PATCH /tasks/{id}"]


def test_list_targets_returns_empty_when_missing(tmp_path: Path) -> None:
    assert list_targets(targets_path=str(tmp_path / "does-not-exist")) == []


def test_assess_weapon_via_mcp_surface(weapons_dir: Path) -> None:
    assessment = assess_weapon(
        weapon_id="resource_ownership_write_isolation",
        weapons_path=str(weapons_dir),
        target=Target(title="Task endpoints", endpoints=["PATCH /tasks/{id}"]),
    )
    assert assessment.proceed is True


def test_default_iteration_specs_returns_four_stages() -> None:
    specs = default_iteration_specs()
    assert [s.name for s in specs] == [
        "baseline",
        "boundary",
        "adversarial_misuse",
        "targeted_escalation",
    ]


def test_assemble_run_report_shapes_output() -> None:
    execution = Drone(InMemoryHttpApi()).run_plan(_AUTHZ_PLAN)
    iteration = IterationRecord(
        spec=IterationSpec(
            index=1,
            name="baseline",
            goal="baseline",
            attacker_prompt="",
            inspector_prompt="",
        ),
        plans=[_AUTHZ_PLAN],
        execution_results=[execution],
        findings=[],
    )

    out = assemble_run_report(
        iterations=[iteration],
        holdout_results=[execution],
        clearance_threshold=0.9,
    )

    assert "risk_report" in out
    assert "clearance" in out
    assert out["clearance"] is not None
    assert out["clearance"]["recommendation"] == "block"


# ---------------------------------------------------------------------------
# Seeded deterministic flaws in the in-memory demo API
# ---------------------------------------------------------------------------


def test_flaw_validation_accepts_invalid_title_type() -> None:
    api = InMemoryHttpApi()
    resp = api.send(
        "userA",
        HttpRequest(method="POST", path="/tasks", body={"title": 12345}),
    )
    assert resp.status_code == 201
    assert resp.body["title"] == 12345
    assert not isinstance(resp.body["title"], str)


def test_flaw_validation_accepts_missing_title() -> None:
    api = InMemoryHttpApi()
    resp = api.send(
        "userA",
        HttpRequest(method="POST", path="/tasks", body={}),
    )
    assert resp.status_code == 201
    assert resp.body["title"] == ""


def test_flaw_list_endpoint_leaks_across_users() -> None:
    api = InMemoryHttpApi()
    api.send("userA", HttpRequest(method="POST", path="/tasks", body={"title": "secret A"}))
    api.send("userB", HttpRequest(method="POST", path="/tasks", body={"title": "secret B"}))

    resp = api.send("userA", HttpRequest(method="GET", path="/tasks"))
    assert resp.status_code == 200
    owners = {t["owner"] for t in resp.body["tasks"]}
    assert "userB" in owners
    assert len(resp.body["tasks"]) == 2


def test_flaw_patch_without_ownership_check() -> None:
    api = InMemoryHttpApi()
    resp = api.send(
        "userA",
        HttpRequest(method="POST", path="/tasks", body={"title": "owned by A"}),
    )
    task_id = resp.body["id"]
    patch_resp = api.send(
        "userB",
        HttpRequest(method="PATCH", path=f"/tasks/{task_id}", body={"title": "hijacked"}),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.body["last_modified_by"] == "userB"
