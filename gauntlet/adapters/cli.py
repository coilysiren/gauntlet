from __future__ import annotations

from ..models import HttpRequest, HttpResponse


class CliAdapter:
    """Execution adapter for CLI surfaces. Not yet implemented."""

    def send(self, user: str, request: HttpRequest) -> HttpResponse:
        raise NotImplementedError
