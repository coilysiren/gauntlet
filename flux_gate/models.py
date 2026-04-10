from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FluxGateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HttpRequest(FluxGateModel):
    method: Literal["GET", "POST", "PATCH"]
    path: str
    body: dict[str, Any] = Field(default_factory=dict)


class HttpResponse(FluxGateModel):
    status_code: int
    body: dict[str, Any] = Field(default_factory=dict)


class Assertion(FluxGateModel):
    kind: Literal["status_code", "invariant"]
    expected: Any | None = None
    rule: str | None = None
    step_index: int
    name: str


class ScenarioStep(FluxGateModel):
    actor: str
    request: HttpRequest


class Scenario(FluxGateModel):
    name: str
    category: str
    goal: str
    steps: list[ScenarioStep]
    assertions: list[Assertion] = Field(default_factory=list)


class ExecutionStepResult(FluxGateModel):
    step_index: int
    actor: str
    request: HttpRequest
    response: HttpResponse


class AssertionResult(FluxGateModel):
    name: str
    kind: Literal["status_code", "invariant"]
    passed: bool
    detail: str


class ExecutionResult(FluxGateModel):
    scenario_name: str
    category: str
    goal: str
    steps: list[ExecutionStepResult]
    assertions: list[AssertionResult]


class Finding(FluxGateModel):
    issue: str
    severity: Literal["low", "medium", "high", "critical"]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    next_targets: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class IterationSpec(FluxGateModel):
    index: int
    name: str
    goal: str
    operator_prompt: str
    adversary_prompt: str


class IterationRecord(FluxGateModel):
    spec: IterationSpec
    scenarios: list[Scenario]
    execution_results: list[ExecutionResult]
    findings: list[Finding]


class RiskReport(FluxGateModel):
    confidence_score: float = Field(ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high", "critical"]
    summary: list[str]
    confirmed_failures: list[str]
    suspicious_patterns: list[str]
    unexplored_surfaces: list[str]
    coverage: list[str]
    conclusion: str


class FluxGateRun(FluxGateModel):
    system_under_test: str
    environment: str
    iterations: list[IterationRecord]
    risk_report: RiskReport
