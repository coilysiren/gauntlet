from __future__ import annotations

from typing import Protocol

from .models import (
    Assertion,
    ExecutionResult,
    Finding,
    IterationRecord,
    IterationSpec,
    Scenario,
    ScenarioStep,
    HttpRequest,
)


class Operator(Protocol):
    def generate_scenarios(
        self, spec: IterationSpec, previous_iterations: list[IterationRecord]
    ) -> list[Scenario]: ...


class Adversary(Protocol):
    def analyze(
        self, spec: IterationSpec, execution_results: list[ExecutionResult]
    ) -> list[Finding]: ...


class DemoOperator:
    def generate_scenarios(
        self, spec: IterationSpec, previous_iterations: list[IterationRecord]
    ) -> list[Scenario]:
        scenario = Scenario(
            name="user_cannot_modify_other_users_task",
            category="authz",
            goal=spec.goal,
            steps=[
                ScenarioStep(
                    actor="userA",
                    request=HttpRequest(
                        method="POST",
                        path="/tasks",
                        body={"title": "private task"},
                    ),
                ),
                ScenarioStep(
                    actor="userB",
                    request=HttpRequest(
                        method="PATCH",
                        path="/tasks/{task_id}",
                        body={"completed": True},
                    ),
                ),
                ScenarioStep(
                    actor="userA",
                    request=HttpRequest(method="GET", path="/tasks/{task_id}"),
                ),
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
                    kind="invariant",
                    rule="task_not_modified_by_other_user",
                    step_index=3,
                ),
            ],
        )

        if spec.index == 1:
            return [scenario]

        return [
            scenario.model_copy(
                update={
                    "name": f"{scenario.name}_{spec.index}",
                    "goal": spec.goal,
                }
            )
        ]


class DemoAdversary:
    def analyze(
        self, spec: IterationSpec, execution_results: list[ExecutionResult]
    ) -> list[Finding]:
        findings: list[Finding] = []
        for result in execution_results:
            failed_assertions = [assertion for assertion in result.assertions if not assertion.passed]
            if not failed_assertions:
                continue

            issue = "unauthorized_cross_user_modification"
            evidence = [f"{assertion.name}: {assertion.detail}" for assertion in failed_assertions]
            findings.append(
                Finding(
                    issue=issue,
                    severity="critical",
                    confidence=0.94,
                    rationale=(
                        "A non-owner mutated another user's task during deterministic local "
                        f"execution in iteration {spec.index}."
                    ),
                    next_targets=[
                        "ownership mutation",
                        "list endpoint visibility",
                        "partial update invariants",
                    ],
                    evidence=evidence,
                )
            )
        return findings
