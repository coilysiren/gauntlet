from __future__ import annotations

from typing import Literal

from .executor import DeterministicLocalExecutor
from .models import Finding, FluxGateRun, IterationRecord, IterationSpec, RiskReport
from .roles import Adversary, Operator


def build_default_iteration_specs() -> list[IterationSpec]:
    return [
        IterationSpec(
            index=1,
            name="broad_baseline",
            goal="broad_baseline",
            operator_prompt="Generate diverse CRUD and lifecycle scenarios.",
            adversary_prompt="Identify anomalies and weak coverage.",
        ),
        IterationSpec(
            index=2,
            name="boundary_and_invariants",
            goal="boundary_and_invariants",
            operator_prompt="Target edge cases, missing fields, and schema drift.",
            adversary_prompt="Escalate invariant violations.",
        ),
        IterationSpec(
            index=3,
            name="adversarial_misuse",
            goal="adversarial_misuse",
            operator_prompt="Simulate auth violations and invalid transitions.",
            adversary_prompt="Identify security and logic failures.",
        ),
        IterationSpec(
            index=4,
            name="targeted_followup",
            goal="targeted_followup",
            operator_prompt="Focus only on suspicious areas.",
            adversary_prompt="Finalize the failure model.",
        ),
    ]


class FluxGateRunner:
    def __init__(
        self,
        executor: DeterministicLocalExecutor,
        operator: Operator,
        adversary: Adversary,
        system_under_test: str = "REST API",
        environment: str = "deterministic_local",
    ) -> None:
        self._executor = executor
        self._operator = operator
        self._adversary = adversary
        self._system_under_test = system_under_test
        self._environment = environment

    def run(self, iterations: list[IterationSpec] | None = None) -> FluxGateRun:
        specs = iterations or build_default_iteration_specs()
        records: list[IterationRecord] = []

        for spec in specs:
            scenarios = self._operator.generate_scenarios(spec, records)
            execution_results = [self._executor.run_scenario(scenario) for scenario in scenarios]
            findings = self._adversary.analyze(spec, execution_results)
            records.append(
                IterationRecord(
                    spec=spec,
                    scenarios=scenarios,
                    execution_results=execution_results,
                    findings=findings,
                )
            )

        return FluxGateRun(
            system_under_test=self._system_under_test,
            environment=self._environment,
            iterations=records,
            risk_report=_build_risk_report(records),
        )


def _build_risk_report(records: list[IterationRecord]) -> RiskReport:
    all_findings = [finding for record in records for finding in record.findings]
    coverage = sorted(
        {
            f"{step.request.method} {step.request.path}"
            for record in records
            for result in record.execution_results
            for step in result.steps
        }
    )
    confirmed_failures = sorted({finding.issue for finding in all_findings})
    suspicious_patterns = sorted(
        {evidence for finding in all_findings for evidence in finding.evidence}
    )
    unexplored_surfaces = _derive_unexplored_surfaces(all_findings)
    confidence_score = _confidence_score(all_findings)
    risk_level = _risk_level(all_findings)

    return RiskReport(
        confidence_score=confidence_score,
        risk_level=risk_level,
        summary=confirmed_failures or ["no confirmed failures detected"],
        confirmed_failures=confirmed_failures,
        suspicious_patterns=suspicious_patterns,
        unexplored_surfaces=unexplored_surfaces,
        coverage=coverage,
        conclusion=_conclusion(risk_level, confirmed_failures),
    )


def _derive_unexplored_surfaces(findings: list[Finding]) -> list[str]:
    if not findings:
        return ["No high-risk unexplored surfaces identified."]
    return sorted({target for finding in findings for target in finding.next_targets})


def _confidence_score(findings: list[Finding]) -> float:
    if not findings:
        return 0.9
    average_finding_confidence = sum(finding.confidence for finding in findings) / len(findings)
    return round(max(0.0, 1.0 - average_finding_confidence), 2)


def _risk_level(findings: list[Finding]) -> Literal["low", "medium", "high", "critical"]:
    if any(finding.severity == "critical" for finding in findings):
        return "critical"
    if any(finding.severity == "high" for finding in findings):
        return "high"
    if any(finding.severity == "medium" for finding in findings):
        return "medium"
    return "low"


def _conclusion(risk_level: str, confirmed_failures: list[str]) -> str:
    if confirmed_failures:
        return (
            "System fails under adversarial pressure and should not be promoted "
            "without remediation."
        )
    return f"System survived the current adversarial loop with {risk_level} risk."
