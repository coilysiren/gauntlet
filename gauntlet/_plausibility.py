"""Heuristic plausibility checks for HoldoutEvaluator plans.

The HoldoutEvaluator subagent composes acceptance plans from blocker text
in-prompt. Nothing in Python validates that the plan actually exercises the
blocker it claims to test — the LLM could write a plan that misses the
point. :func:`check_holdout_plausibility` runs a few cheap pattern matches
against the blocker+plan pair and returns a list of human-readable warnings
the host can surface.

These are heuristics: false positives are expected (the blocker may mention
a concept without the plan literally echoing it), false negatives are
certain (the checks are not exhaustive). The return value is always a list
of strings, never raised as an exception — the host decides whether to act
on the signal.
"""

from __future__ import annotations

import re

from .models import Plan

# Phrases in a blocker that strongly imply the holdout plan should exercise
# at least two distinct users. Kept lowercase so we can match against a
# lowercased blocker.
_CROSS_USER_PHRASES = (
    "non-owner",
    "other user",
    "different user",
    "cross-user",
    "another user",
)

# Match a standalone three-digit status code, 100–599.
_STATUS_CODE_RE = re.compile(r"\b([1-5]\d\d)\b")

# HTTP methods the Plan model permits (see models.HttpRequest).
_METHOD_RE = re.compile(r"\b(GET|POST|PATCH|PUT|DELETE)\b", re.IGNORECASE)


def check_holdout_plausibility(blocker: str, plan: Plan) -> list[str]:
    """Return human-readable warnings about a blocker/plan mismatch.

    Pure function — no side effects. An empty list means no heuristic flagged
    a concern; it does not mean the plan is correct.
    """
    warnings: list[str] = []
    blocker_lower = blocker.lower()

    # --- cross-user mismatch --------------------------------------------------
    mentions_cross_user = any(phrase in blocker_lower for phrase in _CROSS_USER_PHRASES)
    distinct_users = {step.user for step in plan.steps}
    if mentions_cross_user and len(distinct_users) <= 1:
        warnings.append(
            "Blocker implies cross-user behavior but the plan uses only one "
            f"distinct user ({sorted(distinct_users) or '[]'})."
        )

    # --- status-code mismatch -------------------------------------------------
    blocker_status_codes = {int(match) for match in _STATUS_CODE_RE.findall(blocker)}
    if blocker_status_codes:
        # Only consider scalar ``expected`` values for this heuristic. Any-of /
        # range shapes would be richer matcher work; for now, exact match.
        checked_codes: set[int] = set()
        for assertion in plan.assertions:
            if assertion.kind == "status_code" and isinstance(assertion.expected, int):
                checked_codes.add(assertion.expected)
        missing = sorted(blocker_status_codes - checked_codes)
        if missing:
            codes_str = ", ".join(str(c) for c in missing)
            warnings.append(
                f"Blocker mentions status code(s) {codes_str} but no assertion "
                "in the plan checks for that exact code."
            )

    # --- method mismatch ------------------------------------------------------
    blocker_methods = {m.upper() for m in _METHOD_RE.findall(blocker)}
    plan_methods = {step.request.method.upper() for step in plan.steps}
    missing_methods = sorted(blocker_methods - plan_methods)
    if missing_methods:
        methods_str = ", ".join(missing_methods)
        warnings.append(
            f"Blocker mentions HTTP method(s) {methods_str} but no step in the "
            "plan uses that method."
        )

    return warnings


__all__ = ["check_holdout_plausibility"]
