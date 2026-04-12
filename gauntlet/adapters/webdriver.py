from __future__ import annotations

from ..models import HttpRequest, HttpResponse


class WebDriverAdapter:
    """Execution adapter for browser surfaces via WebDriver. Not yet implemented."""

    def send(self, user: str, request: HttpRequest) -> HttpResponse:
        raise NotImplementedError
