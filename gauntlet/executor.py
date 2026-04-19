from __future__ import annotations

from typing import Any

from .http import HttpApi
from .models import (
    Assertion,
    AssertionResult,
    ExecutionResult,
    ExecutionStepResult,
    Plan,
    PlanStep,
)

_MISSING = object()


class Drone:
    def __init__(self, sut: HttpApi) -> None:
        self._sut = sut

    def run_plan(self, plan: Plan) -> ExecutionResult:
        step_results: list[ExecutionStepResult] = []
        context: dict[str, object] = {}
        for index, step in enumerate(plan.steps, start=1):
            request = step.request.model_copy(update={"path": step.request.path.format(**context)})
            send_result = self._sut.send(step.user, request)
            step_results.append(
                ExecutionStepResult(
                    step_index=index,
                    user=step.user,
                    request=request,
                    response=send_result.response,
                    duration_ms=send_result.duration_ms,
                    response_size_bytes=send_result.response_size_bytes,
                    response_headers=send_result.response_headers,
                    outcome=send_result.outcome,
                )
            )
            _apply_extractions(step, send_result.response.body, context)

        assertion_results = [
            _evaluate_assertion(assertion, step_results) for assertion in plan.assertions
        ]
        return ExecutionResult(
            plan_name=plan.name,
            category=plan.category,
            goal=plan.goal,
            steps=step_results,
            assertions=assertion_results,
        )


def _apply_extractions(step: PlanStep, body: dict[str, Any], context: dict[str, object]) -> None:
    """Write template-variable captures from ``body`` into ``context``.

    Generic ``step.extract`` entries are applied first. The ``/tasks`` →
    ``task_id`` shortcut is a legacy-compat carve-out for plans written before
    ``extract`` existed; new plans should set ``extract={"task_id": "id"}``
    explicitly instead of relying on the hardcoded path match.
    """
    for var_name, body_path in step.extract.items():
        value = _lookup_dotted(body, body_path)
        if value is not _MISSING:
            context[var_name] = value

    # Legacy backward-compat: pre-``extract`` plans that POST to /tasks used to
    # auto-populate {task_id}. Only kick in when the caller didn't opt into
    # explicit extraction, so new plans retain full control.
    if (
        not step.extract
        and step.request.method == "POST"
        and step.request.path == "/tasks"
        and "id" in body
    ):
        context["task_id"] = body["id"]


def _lookup_dotted(body: dict[str, Any], path: str) -> Any:
    """Return the value at ``path`` inside ``body`` or ``_MISSING``.

    ``path`` is a dotted key like ``id`` or ``data.id``. Any missing segment
    or non-dict traversal short-circuits to ``_MISSING``.
    """
    current: Any = body
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return _MISSING
        current = current[segment]
    return current


def _evaluate_assertion(
    assertion: Assertion, step_results: list[ExecutionStepResult]
) -> AssertionResult:
    step_result = step_results[assertion.step_index - 1]
    actual = step_result.response.status_code
    passed, detail = _match_status_code(assertion.expected, actual)
    return AssertionResult(name=assertion.name, passed=passed, detail=detail)


def _match_status_code(expected: Any, actual: int) -> tuple[bool, str]:
    """Compare ``actual`` against the ``expected`` matcher shape.

    Supported shapes:

    - scalar (``int``) — exact equality (legacy behavior).
    - ``list`` — any-of: actual must be in the list.
    - ``dict`` with ``min``/``max`` — inclusive range, either bound optional.
    - ``dict`` with ``not`` — negation: actual must not equal the value.
    - ``dict`` with ``in`` — explicit any-of, same semantics as the list form.

    Any other shape produces a failing assertion with a descriptive detail
    rather than raising; the evaluator is called inside the host-facing
    tool boundary and should never blow up on a malformed plan.
    """
    if isinstance(expected, dict):
        return _match_dict(expected, actual)
    if isinstance(expected, list):
        passed = actual in expected
        return passed, f"expected status in {expected}, got {actual}"
    # Fallback: scalar equality (covers int, None, str — legacy shape).
    passed = actual == expected
    return passed, f"expected status {expected}, got {actual}"


def _match_dict(expected: dict[str, Any], actual: int) -> tuple[bool, str]:
    """Dispatch dict-shaped matchers.

    Exactly one recognized key must be present. Multiple keys, unrecognized
    keys, or a missing key produce a failing assertion with a clear detail.
    """
    keys = set(expected.keys())
    if keys == {"not"}:
        target = expected["not"]
        return actual != target, f"expected status != {target}, got {actual}"
    if keys == {"in"}:
        options = expected["in"]
        if not isinstance(options, list):
            return False, f"invalid matcher {expected!r}: 'in' value must be a list"
        return actual in options, f"expected status in {options}, got {actual}"
    if keys <= {"min", "max"} and keys:
        lo = expected.get("min")
        hi = expected.get("max")
        if lo is not None and not isinstance(lo, int):
            return False, f"invalid matcher {expected!r}: 'min' must be int"
        if hi is not None and not isinstance(hi, int):
            return False, f"invalid matcher {expected!r}: 'max' must be int"
        lo_ok = lo is None or actual >= lo
        hi_ok = hi is None or actual <= hi
        passed = lo_ok and hi_ok
        bounds = []
        if lo is not None:
            bounds.append(f">= {lo}")
        if hi is not None:
            bounds.append(f"<= {hi}")
        return passed, f"expected status {' and '.join(bounds)}, got {actual}"
    return False, f"invalid matcher {expected!r}: unsupported shape"
