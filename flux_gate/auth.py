from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from .models import FluxGateModel


class BearerAuth(FluxGateModel):
    """HTTP Bearer token: ``Authorization: Bearer <token>``."""

    type: Literal["bearer"]
    token: str


class ApiKeyAuth(FluxGateModel):
    """Arbitrary header authentication (e.g. ``X-API-Key``, ``X-Auth-Token``)."""

    type: Literal["api_key"]
    header: str
    key: str


ActorAuth = Annotated[BearerAuth | ApiKeyAuth, Field(discriminator="type")]


class ActorsConfig(FluxGateModel):
    """Actor authentication configuration loaded from a YAML file.

    Each key is an actor name.  Each value describes how to authenticate
    that actor against the system under test.

    Example YAML::

        actors:
          alice:
            type: bearer
            token: "eyJ..."
          bob:
            type: api_key
            header: X-API-Key
            key: "secret-b"

    Actors omitted from this file fall back to the default ``X-Actor: <name>``
    header that ``HttpExecutor`` sends automatically.
    """

    actors: dict[str, Annotated[BearerAuth | ApiKeyAuth, Field(discriminator="type")]]


def to_actor_headers(config: ActorsConfig) -> dict[str, dict[str, str]]:
    """Convert an ``ActorsConfig`` into the ``actor_headers`` dict expected by ``HttpExecutor``."""
    headers: dict[str, dict[str, str]] = {}
    for actor, auth in config.actors.items():
        if isinstance(auth, BearerAuth):
            headers[actor] = {"Authorization": f"Bearer {auth.token}"}
        else:
            headers[actor] = {auth.header: auth.key}
    return headers
