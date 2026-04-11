from __future__ import annotations

import os
from typing import Annotated, Literal

from pydantic import Field

from .models import GauntletModel


class BearerAuth(GauntletModel):
    """HTTP Bearer token: ``Authorization: Bearer <value>``.

    ``token_env`` is the name of the environment variable that holds the token.
    The actual secret is never written to the config file.
    """

    type: Literal["bearer"]
    token_env: str


class ApiKeyAuth(GauntletModel):
    """Arbitrary header authentication (e.g. ``X-API-Key``, ``X-Auth-Token``).

    ``key_env`` is the name of the environment variable that holds the key value.
    The actual secret is never written to the config file.
    """

    type: Literal["api_key"]
    header: str
    key_env: str


UserAuth = Annotated[BearerAuth | ApiKeyAuth, Field(discriminator="type")]


class UsersConfig(GauntletModel):
    """Actor authentication configuration loaded from ``.gauntlet/users.yaml``.

    Each key is an user name.  Each value names the environment variables that
    hold that user's credentials — secrets are never stored in the config file.

    Example YAML::

        users:
          alice:
            type: bearer
            token_env: ALICE_TOKEN
          bob:
            type: api_key
            header: X-API-Key
            key_env: BOB_API_KEY

    Actors omitted from this file fall back to the default ``X-User: <name>``
    header that ``HttpExecutor`` sends automatically.
    """

    users: dict[str, Annotated[BearerAuth | ApiKeyAuth, Field(discriminator="type")]]


def to_user_headers(config: UsersConfig) -> dict[str, dict[str, str]]:
    """Resolve env var references in an ``UsersConfig`` into request headers.

    Raises ``ValueError`` if a referenced environment variable is not set.
    """
    headers: dict[str, dict[str, str]] = {}
    for user, auth in config.users.items():
        if isinstance(auth, BearerAuth):
            token = os.environ.get(auth.token_env)
            if token is None:
                raise ValueError(f"Actor {user!r}: env var {auth.token_env!r} is not set")
            headers[user] = {"Authorization": f"Bearer {token}"}
        else:
            key = os.environ.get(auth.key_env)
            if key is None:
                raise ValueError(f"Actor {user!r}: env var {auth.key_env!r} is not set")
            headers[user] = {auth.header: key}
    return headers
