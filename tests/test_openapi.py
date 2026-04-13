"""Tests for gauntlet.openapi — OpenAPI 3.x spec parsing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from gauntlet.openapi import parse_openapi

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MINIMAL_SPEC: dict[str, object] = {
    "openapi": "3.0.3",
    "info": {"title": "Pet Store", "version": "1.0.0"},
    "paths": {
        "/pets": {
            "get": {
                "summary": "List pets",
                "parameters": [
                    {"name": "limit", "in": "query", "schema": {"type": "integer"}},
                ],
            },
            "post": {
                "summary": "Create a pet",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "tag": {"type": "string"},
                                },
                            }
                        }
                    }
                },
            },
        },
        "/pets/{petId}": {
            "parameters": [
                {"name": "petId", "in": "path", "required": True, "schema": {"type": "string"}},
            ],
            "get": {"summary": "Get a pet"},
            "delete": {"summary": "Delete a pet"},
        },
    },
}

_SPEC_WITH_REFS: dict[str, object] = {
    "openapi": "3.0.3",
    "info": {"title": "Ref Test", "version": "0.1.0"},
    "paths": {
        "/items": {
            "post": {
                "summary": "Create item",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Item"},
                        }
                    }
                },
            },
        },
    },
    "components": {
        "schemas": {
            "Item": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "label": {"type": "string"},
                },
            }
        }
    },
}


def _write_yaml(tmp_path: Path, data: dict[str, object], name: str = "spec.yaml") -> str:
    p = tmp_path / name
    p.write_text(yaml.dump(data, sort_keys=False))
    return str(p)


def _write_json(tmp_path: Path, data: dict[str, object], name: str = "spec.json") -> str:
    p = tmp_path / name
    p.write_text(json.dumps(data))
    return str(p)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParseOpenapi:
    """Core parsing behaviour."""

    def test_yaml_spec_returns_correct_number_of_targets(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _MINIMAL_SPEC)
        targets = parse_openapi(path)
        # GET /pets, POST /pets, GET /pets/{petId}, DELETE /pets/{petId}
        assert len(targets) == 4

    def test_json_spec_returns_same_targets(self, tmp_path: Path) -> None:
        yaml_path = _write_yaml(tmp_path, _MINIMAL_SPEC)
        json_path = _write_json(tmp_path, _MINIMAL_SPEC, "spec.json")
        yaml_targets = parse_openapi(yaml_path)
        json_targets = parse_openapi(json_path)
        assert len(yaml_targets) == len(json_targets)
        assert {t.title for t in yaml_targets} == {t.title for t in json_targets}

    def test_endpoints_use_method_space_path(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _MINIMAL_SPEC)
        targets = parse_openapi(path)
        endpoints = {e for t in targets for e in t.endpoints}
        assert "GET /pets" in endpoints
        assert "POST /pets" in endpoints
        assert "GET /pets/{petId}" in endpoints
        assert "DELETE /pets/{petId}" in endpoints

    def test_params_appear_in_title(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _MINIMAL_SPEC)
        targets = parse_openapi(path)
        get_pets = next(t for t in targets if "GET /pets" in t.endpoints)
        assert "limit(query)" in get_pets.title

    def test_path_level_params_inherited(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _MINIMAL_SPEC)
        targets = parse_openapi(path)
        get_pet = next(t for t in targets if "GET /pets/{petId}" in t.endpoints)
        assert "petId(path)" in get_pet.title

    def test_request_body_in_title(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _MINIMAL_SPEC)
        targets = parse_openapi(path)
        post_pets = next(t for t in targets if "POST /pets" in t.endpoints)
        assert "body=" in post_pets.title
        assert "name:string" in post_pets.title

    def test_ref_resolved(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _SPEC_WITH_REFS)
        targets = parse_openapi(path)
        assert len(targets) == 1
        t = targets[0]
        assert "POST /items" in t.endpoints
        assert "id:integer" in t.title
        assert "label:string" in t.title

    def test_empty_paths(self, tmp_path: Path) -> None:
        spec: dict[str, object] = {
            "openapi": "3.0.3",
            "info": {"title": "Empty", "version": "0.0.1"},
            "paths": {},
        }
        path = _write_yaml(tmp_path, spec)
        assert parse_openapi(path) == []

    def test_invalid_top_level_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("- just a list")
        with pytest.raises(ValueError, match="mapping"):
            parse_openapi(str(p))
