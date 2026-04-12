from __future__ import annotations

from typing import Protocol

from ..models import HttpRequest, HttpResponse
from .cli import CliAdapter
from .http import HttpApi, InMemoryHttpApi
from .webdriver import WebDriverAdapter

__all__ = [
    "Adapter",
    "CliAdapter",
    "HttpApi",
    "InMemoryHttpApi",
    "WebDriverAdapter",
]


class Adapter(Protocol):
    def send(self, user: str, request: HttpRequest) -> HttpResponse: ...
