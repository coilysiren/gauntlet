"""Parse OpenAPI 3.x specs into gauntlet Target objects.

Supports both YAML and JSON files.  Extracts every path+method combination
along with its parameters and request-body schema, producing one ``Target``
per endpoint.  The resulting list can be fed directly into the adversarial
loop via the CLI ``--openapi`` flag.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .models import Target


def _read_spec(source: str) -> dict[str, Any]:
    """Read an OpenAPI spec from a file path and return the parsed dict."""
    path = Path(source)
    text = path.read_text()
    # Try JSON first; fall back to YAML (which is a superset of JSON anyway).
    try:
        data: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping at the top level, got {type(data).__name__}")
    return data


def _summarise_schema(schema: dict[str, Any] | None) -> str:
    """Return a compact human-readable summary of a JSON Schema object."""
    if not schema:
        return ""
    parts: list[str] = []
    schema_type = schema.get("type", "object")
    properties = schema.get("properties", {})
    if properties:
        for name, prop in properties.items():
            prop_type = prop.get("type", "any")
            parts.append(f"{name}:{prop_type}")
    if parts:
        return f"{schema_type}{{{', '.join(parts)}}}"
    return str(schema_type)


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    """Resolve a ``$ref`` pointer (only ``#/components/...`` style)."""
    if not ref.startswith("#/"):
        return {}
    parts = ref.lstrip("#/").split("/")
    node: Any = spec
    for part in parts:
        if isinstance(node, dict):
            node = node.get(part, {})
        else:
            return {}
    if isinstance(node, dict):
        return node
    return {}


def _resolve_maybe(spec: dict[str, Any], obj: dict[str, Any]) -> dict[str, Any]:
    """If *obj* contains ``$ref``, resolve it; otherwise return *obj* as-is."""
    ref = obj.get("$ref")
    if isinstance(ref, str):
        return _resolve_ref(spec, ref)
    return obj


_VALID_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def parse_openapi(source: str) -> list[Target]:
    """Parse an OpenAPI 3.x spec file and return a ``Target`` per endpoint.

    Each target's ``title`` is ``"METHOD /path"`` (e.g. ``"GET /pets/{id}"``),
    and its ``endpoints`` list contains the same string so existing weapon
    matching logic works unchanged.

    Parameters
    ----------
    source:
        Filesystem path to an OpenAPI YAML or JSON file.

    Returns
    -------
    list[Target]
        One target per path+method combination found in the spec.
    """
    spec = _read_spec(source)

    paths: dict[str, Any] = spec.get("paths", {})
    targets: list[Target] = []

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        # Path-level parameters apply to every operation under this path.
        path_params: list[dict[str, Any]] = path_item.get("parameters", [])

        for method, operation in path_item.items():
            if method not in _VALID_METHODS:
                continue
            if not isinstance(operation, dict):
                continue

            method_upper = method.upper()
            endpoint = f"{method_upper} {path}"

            # Merge path-level and operation-level parameters.
            op_params: list[dict[str, Any]] = operation.get("parameters", [])
            all_params = path_params + op_params

            param_parts: list[str] = []
            for p in all_params:
                p = _resolve_maybe(spec, p)
                p_name = p.get("name", "?")
                p_in = p.get("in", "?")
                param_parts.append(f"{p_name}({p_in})")

            # Request body schema summary.
            body_summary = ""
            request_body = operation.get("requestBody")
            if isinstance(request_body, dict):
                request_body = _resolve_maybe(spec, request_body)
                content = request_body.get("content", {})
                json_media = content.get("application/json", {})
                if isinstance(json_media, dict):
                    schema = json_media.get("schema")
                    if isinstance(schema, dict):
                        schema = _resolve_maybe(spec, schema)
                        body_summary = _summarise_schema(schema)

            # Build a descriptive title.
            title_parts = [endpoint]
            if param_parts:
                title_parts.append(f"params=[{', '.join(param_parts)}]")
            if body_summary:
                title_parts.append(f"body={body_summary}")

            targets.append(Target(title=" ".join(title_parts), endpoints=[endpoint]))

    return targets
