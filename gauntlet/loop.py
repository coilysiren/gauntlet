from __future__ import annotations

from typing import Literal

from .models import (
    Clearance,
    ExecutionResult,
    FinalClearance,
    Finding,
    IterationRecord,
    RiskReport,
    WeaponReport,
)


def build_risk_report(
    records: list[IterationRecord],
    holdout_results: list[ExecutionResult],
    clearance_threshold: float,
) -> tuple[RiskReport, Clearance | None]:
    """Assemble a ``RiskReport`` and optional ``Clearance`` from iteration records.

    ``records`` is the full per-iteration log the host has accumulated.
    ``holdout_results`` are the execution results of the weapon's acceptance
    plans (the withheld vitals). When ``holdout_results`` is empty, the
    returned clearance is ``None`` — there's no gate to evaluate.
    """
    all_findings = [finding for record in records for finding in record.findings]
    blocker_findings = [f for f in all_findings if not f.is_anomaly]
    anomaly_findings = [f for f in all_findings if f.is_anomaly]
    coverage = sorted(
        {
            f"{step.request.method} {step.request.path}"
            for record in records
            for result in record.execution_results
            for step in result.steps
        }
    )
    confirmed_failures = sorted({finding.issue for finding in blocker_findings})
    suspicious_patterns = sorted(
        {item.content for finding in blocker_findings for item in finding.evidence}
    )
    anomalies = sorted({finding.issue for finding in anomaly_findings})
    unexplored_surfaces = _derive_unexplored_surfaces(all_findings)
    confidence_score = _confidence_score(records, coverage)
    risk_level = _risk_level(blocker_findings)

    clearance = _build_clearance(holdout_results, clearance_threshold) if holdout_results else None

    report = RiskReport(
        confidence_score=confidence_score,
        risk_level=risk_level,
        summary=confirmed_failures or ["no confirmed failures detected"],
        confirmed_failures=confirmed_failures,
        suspicious_patterns=suspicious_patterns,
        unexplored_surfaces=unexplored_surfaces,
        anomalies=anomalies,
        coverage=coverage,
        conclusion=_conclusion(risk_level, confirmed_failures),
    )
    return report, clearance


def _build_clearance(holdout_results: list[ExecutionResult], threshold: float) -> Clearance:
    satisfaction_score = sum(r.satisfaction_score for r in holdout_results) / len(holdout_results)
    passed = satisfaction_score >= threshold

    if satisfaction_score >= threshold:
        recommendation: Literal["pass", "conditional", "block"] = "pass"
        rationale = (
            f"Holdout satisfaction score {satisfaction_score:.0%} meets threshold {threshold:.0%}."
        )
    elif satisfaction_score >= threshold * 0.8:
        recommendation = "conditional"
        rationale = (
            f"Holdout satisfaction score {satisfaction_score:.0%} is below threshold "
            f"{threshold:.0%} but within 20% — human review recommended."
        )
    else:
        recommendation = "block"
        rationale = (
            f"Holdout satisfaction score {satisfaction_score:.0%} "
            f"is below threshold {threshold:.0%}."
        )

    return Clearance(
        passed=passed,
        holdout_satisfaction_score=satisfaction_score,
        threshold=threshold,
        recommendation=recommendation,
        rationale=rationale,
    )


def _derive_unexplored_surfaces(findings: list[Finding]) -> list[str]:
    if not findings:
        return ["No high-risk unexplored surfaces identified."]
    return sorted({surface for finding in findings for surface in finding.next_targets})


def _confidence_score(records: list[IterationRecord], coverage: list[str]) -> float:
    """Coverage confidence: how thoroughly the attack surface was explored.

    Composed of three signals:
    - Plan diversity: distinct attack categories relative to iterations run.
    - Surface exploration depth: unique endpoints hit vs endpoints targeted.
    - Exploration completeness: next_targets flagged by findings but not yet covered.
    """
    if not records:
        return 0.0

    all_plans = [plan for record in records for plan in record.plans]
    distinct_categories = len({plan.category for plan in all_plans}) if all_plans else 0
    plan_diversity = min(1.0, distinct_categories / len(records))

    targeted = [
        endpoint
        for record in records
        if record.spec.target
        for endpoint in record.spec.target.endpoints
    ]
    if targeted:
        surface_depth = min(1.0, len(coverage) / len(targeted))
    else:
        surface_depth = min(1.0, len(coverage) / max(1, len(records) * 2))

    all_findings = [finding for record in records for finding in record.findings]
    next_targets = {surface for finding in all_findings for surface in finding.next_targets}
    if next_targets:
        uncovered = len(next_targets - set(coverage))
        exploration_completeness = 1.0 - (uncovered / len(next_targets))
    else:
        exploration_completeness = 1.0

    return round(plan_diversity * 0.35 + surface_depth * 0.35 + exploration_completeness * 0.30, 2)


def _risk_level(findings: list[Finding]) -> Literal["low", "medium", "high"]:
    if any(finding.severity == "high" for finding in findings):
        return "high"
    if any(finding.severity == "medium" for finding in findings):
        return "medium"
    return "low"


_RISK_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


def aggregate_final_clearance(
    per_weapon: list[WeaponReport], clearance_threshold: float
) -> FinalClearance:
    """Aggregate per-weapon reports into one overall pass/fail decision.

    Used by the ``assemble_final_clearance`` MCP tool. See
    :class:`FinalClearance` for the aggregation rules.
    """
    if not per_weapon:
        return FinalClearance(
            overall_confidence=0.0,
            max_risk_level="low",
            all_confirmed_failures=[],
            final_recommendation="block",
            rationale="No weapons were run; nothing can be cleared.",
            clearance_threshold=clearance_threshold,
            per_weapon_reports=[],
        )

    confidence_signals: list[float] = []
    for wr in per_weapon:
        confidence_signals.append(wr.risk_report.confidence_score)
        if wr.clearance is not None:
            confidence_signals.append(wr.clearance.holdout_satisfaction_score)
    overall_confidence = round(min(confidence_signals), 4)

    max_risk_rank = max(_RISK_RANK[wr.risk_report.risk_level] for wr in per_weapon)
    max_risk_level: Literal["low", "medium", "high"]
    if max_risk_rank == _RISK_RANK["high"]:
        max_risk_level = "high"
    elif max_risk_rank == _RISK_RANK["medium"]:
        max_risk_level = "medium"
    else:
        max_risk_level = "low"

    all_confirmed_failures = sorted(
        {failure for wr in per_weapon for failure in wr.risk_report.confirmed_failures}
    )

    has_high = max_risk_rank == _RISK_RANK["high"]
    has_medium = any(wr.risk_report.risk_level == "medium" for wr in per_weapon)
    threshold_met = overall_confidence >= clearance_threshold

    final_recommendation: Literal["pass", "conditional", "block"]
    if threshold_met and not has_high and not has_medium:
        final_recommendation = "pass"
        rationale = (
            f"Overall confidence {overall_confidence:.0%} meets threshold "
            f"{clearance_threshold:.0%} and no medium- or high-risk findings."
        )
    elif threshold_met and not has_high:
        final_recommendation = "conditional"
        rationale = (
            f"Overall confidence {overall_confidence:.0%} meets threshold "
            f"{clearance_threshold:.0%} but at least one weapon surfaced "
            f"medium-severity findings — human review recommended."
        )
    else:
        final_recommendation = "block"
        if has_high:
            rationale = "At least one weapon surfaced high-severity findings; promotion is blocked."
        else:
            rationale = (
                f"Overall confidence {overall_confidence:.0%} is below threshold "
                f"{clearance_threshold:.0%}."
            )

    return FinalClearance(
        overall_confidence=overall_confidence,
        max_risk_level=max_risk_level,
        all_confirmed_failures=all_confirmed_failures,
        final_recommendation=final_recommendation,
        rationale=rationale,
        clearance_threshold=clearance_threshold,
        per_weapon_reports=per_weapon,
    )


def _conclusion(risk_level: str, confirmed_failures: list[str]) -> str:
    if confirmed_failures:
        return (
            "System fails under adversarial pressure and should not be promoted "
            "without remediation."
        )
    return f"System survived the current adversarial loop with {risk_level} risk."
