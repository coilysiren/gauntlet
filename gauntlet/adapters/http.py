from __future__ import annotations

from copy import deepcopy
from typing import Any

import requests as http

from ..models import Action, HttpRequest, HttpResponse, Observation


class HttpApi:
    """Sends real HTTP requests to a locally-running API process.

    Each user is identified by an ``X-User`` header by default. Pass
    ``user_headers`` to override with bearer tokens or session cookies.

    Example::

        adapter = HttpApi(
            "http://localhost:8000",
            user_headers={
                "userA": {"Authorization": "Bearer token-a"},
                "userB": {"Authorization": "Bearer token-b"},
            },
        )
    """

    def __init__(
        self,
        base_url: str,
        user_headers: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_headers = user_headers or {}

    def send(self, user: str, request: HttpRequest) -> HttpResponse:
        headers = {"X-User": user, **self._user_headers.get(user, {})}
        resp = http.request(
            request.method,
            f"{self._base_url}{request.path}",
            json=request.body if request.body else None,
            headers=headers,
            timeout=10,
        )
        body: dict[str, Any]
        try:
            body = resp.json()
        except ValueError:
            body = {"_raw": resp.text}
        return HttpResponse(status_code=resp.status_code, body=body)

    def execute(self, user: str, action: Action) -> Observation:
        response = self.send(user, action.to_http_request())
        return Observation.from_http_response(response)


class InMemoryHttpApi:
    """Demo REST API with intentional, deterministic flaws.

    Seeded flaws (all deterministic, no randomness):

    1. **PATCH without ownership check** — any user can modify any task.
    2. **No input validation on POST** — ``title`` accepts non-string types
       (e.g. integers, lists) and the ``completed`` field accepts any truthy
       value instead of requiring a boolean.
    3. **GET /tasks leaks all tasks** — the list endpoint returns every task
       in the store regardless of the requesting user's ownership.
    """

    def __init__(self) -> None:
        self._tasks: dict[int, dict[str, object]] = {}
        self._next_id = 1

    def send(self, user: str, request: HttpRequest) -> HttpResponse:
        if request.method == "POST" and request.path == "/tasks":
            return self._create_task(user, request)
        if request.method == "GET" and request.path == "/tasks":
            return self._list_tasks(user, request)
        if request.method == "GET" and request.path.startswith("/tasks/"):
            return self._get_task(user, request)
        if request.method == "PATCH" and request.path.startswith("/tasks/"):
            return self._patch_task(user, request)
        return HttpResponse(status_code=404, body={"error": "not_found"})

    def execute(self, user: str, action: Action) -> Observation:
        response = self.send(user, action.to_http_request())
        return Observation.from_http_response(response)

    def _create_task(self, user: str, request: HttpRequest) -> HttpResponse:
        # Seeded flaw: no validation on title or completed fields.
        # title accepts any JSON type (int, list, dict, null) instead of
        # requiring a string; completed accepts any truthy value instead of
        # requiring a boolean.  A correct API would reject non-string titles
        # with 422.
        task_id = self._next_id
        self._next_id += 1
        task = {
            "id": task_id,
            "owner": user,
            "title": request.body.get("title", ""),
            "completed": bool(request.body.get("completed", False)),
        }
        self._tasks[task_id] = task
        return HttpResponse(status_code=201, body=deepcopy(task))

    def _list_tasks(self, user: str, request: HttpRequest) -> HttpResponse:
        # Seeded flaw: returns ALL tasks regardless of ownership.
        # A correct API would filter to only tasks owned by the requesting user.
        _ = user  # user intentionally ignored — this is the flaw
        all_tasks = [deepcopy(t) for t in self._tasks.values()]
        return HttpResponse(status_code=200, body={"tasks": all_tasks})

    def _get_task(self, user: str, request: HttpRequest) -> HttpResponse:
        task = self._tasks.get(_task_id_from_path(request.path))
        if task is None:
            return HttpResponse(status_code=404, body={"error": "not_found"})
        if task["owner"] != user:
            return HttpResponse(status_code=403, body={"error": "forbidden"})
        return HttpResponse(status_code=200, body=deepcopy(task))

    def _patch_task(self, user: str, request: HttpRequest) -> HttpResponse:
        task = self._tasks.get(_task_id_from_path(request.path))
        if task is None:
            return HttpResponse(status_code=404, body={"error": "not_found"})

        # Seeded flaw: no ownership check — any user can modify any task.
        task["title"] = request.body.get("title", task["title"])
        task["completed"] = request.body.get("completed", task["completed"])
        task["last_modified_by"] = user
        return HttpResponse(status_code=200, body=deepcopy(task))


def _task_id_from_path(path: str) -> int:
    return int(path.rsplit("/", maxsplit=1)[-1])
