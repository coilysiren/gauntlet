from __future__ import annotations

import re
from typing import Protocol

from .models import Target, Weapon, WeaponAssessment


class WeaponAssessor(Protocol):
    """Evaluates a Weapon for quality before the adversarial loop runs.

    Returns a ``WeaponAssessment`` with a quality score, issues, suggestions,
    and a ``proceed`` flag. When ``proceed`` is ``False``, the host should
    skip the weapon.
    """

    def assess(self, weapon: Weapon, target: Target | None) -> WeaponAssessment: ...


class DemoWeaponAssessor:
    """Heuristic weapon assessor that runs without an LLM.

    Scores a Weapon based on:
    - blocker length  (short blockers score low)
    - presence of specific HTTP status codes in blockers  (score high)
    - presence of target endpoints  (score high)

    A ``quality_score`` below 0.5 sets ``proceed=False``, blocking the run.
    """

    _MIN_CRITERION_LEN = 20
    _STATUS_CODE_RE = re.compile(r"\b[1-5]\d{2}\b")

    def assess(self, weapon: Weapon, target: Target | None) -> WeaponAssessment:
        issues: list[str] = []
        suggestions: list[str] = []
        score = 1.0

        for criterion in weapon.blockers:
            if len(criterion.strip()) < self._MIN_CRITERION_LEN:
                issues.append(
                    f"Blocker too vague (< {self._MIN_CRITERION_LEN} chars): {criterion!r}"
                )
                suggestions.append(
                    "Specify expected status codes, fields, or observable behaviour."
                )
                score -= 0.3

        if target is None or not target.endpoints:
            issues.append("No target endpoints specified.")
            suggestions.append("List the endpoints the weapon covers (e.g. 'PATCH /tasks/{id}').")
            score -= 0.2

        has_status_code = any(self._STATUS_CODE_RE.search(c) for c in weapon.blockers)
        if not has_status_code:
            suggestions.append("Consider adding expected HTTP status codes to blockers.")
            score -= 0.1

        quality_score = round(max(0.0, score), 4)
        return WeaponAssessment(
            quality_score=quality_score,
            issues=issues,
            suggestions=suggestions,
            proceed=quality_score >= 0.5,
        )
