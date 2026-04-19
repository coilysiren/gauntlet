from __future__ import annotations

import json
import os
from pathlib import Path

import yaml
from click.testing import CliRunner

from gauntlet import (
    DemoAttacker,
    DemoInspector,
    Drone,
    GauntletRunner,
    InMemoryHttpApi,
)
from gauntlet.cli import (
    EXIT_BLOCKED,
    EXIT_CLEARANCE,
    EXIT_CONFIG_ERROR,
    EXIT_RUNTIME_ERROR,
    _load_config_file,
    _serialize_run,
    main,
)


def test_load_config_file_returns_empty_when_no_default(tmp_path: Path) -> None:
    """When no explicit path and no default file exists, return empty dict."""
    original = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert _load_config_file(None) == {}
    finally:
        os.chdir(original)


def test_load_config_file_reads_explicit_path(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(yaml.dump({"url": "http://example.com", "threshold": 0.5}))
    result = _load_config_file(str(cfg))
    assert result["url"] == "http://example.com"
    assert result["threshold"] == 0.5


def test_load_config_file_reads_default(tmp_path: Path) -> None:
    """When no explicit path is given, .gauntlet/config.yaml is loaded if present."""
    (tmp_path / ".gauntlet").mkdir()
    (tmp_path / ".gauntlet" / "config.yaml").write_text(
        yaml.dump({"url": "http://default.local", "weapon": "/custom/weapons"})
    )
    original = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = _load_config_file(None)
        assert result["url"] == "http://default.local"
        assert result["weapon"] == "/custom/weapons"
    finally:
        os.chdir(original)


def test_load_config_file_exits_on_missing_explicit(tmp_path: Path) -> None:
    """An explicit --config pointing to a missing file exits with config-error code."""
    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(tmp_path / "nope.yaml")])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "config file not found" in result.output


def test_cli_url_from_config_file(tmp_path: Path) -> None:
    """URL can be provided via config file instead of positional argument."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(yaml.dump({"url": "http://from-config.local"}))
    runner = CliRunner()
    # Will fail due to missing env vars, but should get past URL validation
    result = runner.invoke(main, ["--config", str(cfg)])
    assert "URL is required" not in result.output
    assert "missing required environment variables" in result.output


def test_cli_flag_overrides_config(tmp_path: Path) -> None:
    """CLI flags take precedence over config file values."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(yaml.dump({"url": "http://config-url.local", "threshold": 0.5}))
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["http://cli-url.local", "--config", str(cfg), "--threshold", "0.75"],
    )
    # Should get past URL validation with CLI url, fail on env vars
    assert "URL is required" not in result.output
    assert "missing required environment variables" in result.output


def test_cli_requires_url(tmp_path: Path) -> None:
    """Without URL in args or config, exit with config-error code."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(yaml.dump({"weapon": "/some/path"}))
    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(cfg)])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "URL is required" in result.output


def test_cli_missing_env_vars_exits_config_error(tmp_path: Path) -> None:
    """Missing GAUNTLET_* env vars are a config error (exit 3)."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(yaml.dump({"url": "http://example.com"}))
    runner = CliRunner()
    env = {
        "GAUNTLET_ATTACKER_TYPE": "",
        "GAUNTLET_ATTACKER_KEY": "",
        "GAUNTLET_INSPECTOR_TYPE": "",
        "GAUNTLET_INSPECTOR_KEY": "",
    }
    result = runner.invoke(main, ["--config", str(cfg)], env=env)
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "missing required environment variables" in result.output


def test_cli_unknown_provider_exits_config_error(tmp_path: Path) -> None:
    """An unknown LLM provider type is a config error (exit 3), not a runtime error."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(yaml.dump({"url": "http://example.com"}))
    runner = CliRunner()
    env = {
        "GAUNTLET_ATTACKER_TYPE": "nonexistent",
        "GAUNTLET_ATTACKER_KEY": "x",
        "GAUNTLET_INSPECTOR_TYPE": "nonexistent",
        "GAUNTLET_INSPECTOR_KEY": "x",
    }
    result = runner.invoke(main, ["--config", str(cfg)], env=env)
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "Unknown LLM provider" in result.output


def test_exit_code_taxonomy_constants() -> None:
    """The taxonomy is a stable contract — pin the numeric values."""
    assert EXIT_CLEARANCE == 0
    assert EXIT_BLOCKED == 1
    assert EXIT_RUNTIME_ERROR == 2
    assert EXIT_CONFIG_ERROR == 3


def test_config_fail_fast_hyphen(tmp_path: Path) -> None:
    """Config files using 'fail-fast' (with hyphen) are handled correctly."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(yaml.dump({"url": "http://example.com", "fail-fast": False}))
    result = _load_config_file(str(cfg))
    assert result["fail-fast"] is False


def _demo_run() -> object:
    runner = GauntletRunner(
        executor=Drone(InMemoryHttpApi()),
        attacker=DemoAttacker(),
        inspector=DemoInspector(),
    )
    return runner.run()


def test_serialize_run_yaml_default() -> None:
    """Default YAML serialization produces a parseable mapping."""
    run = _demo_run()
    out = _serialize_run(run, "yaml")  # type: ignore[arg-type]
    parsed = yaml.safe_load(out)
    assert isinstance(parsed, dict)
    assert "iterations" in parsed
    assert "risk_report" in parsed


def test_serialize_run_json_format() -> None:
    """JSON serialization produces parseable JSON with the same top-level keys."""
    run = _demo_run()
    out = _serialize_run(run, "json")  # type: ignore[arg-type]
    parsed = json.loads(out)
    assert isinstance(parsed, dict)
    assert "iterations" in parsed
    assert "risk_report" in parsed


def test_cli_invalid_format_exits(tmp_path: Path) -> None:
    """An unsupported --format value is rejected."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(yaml.dump({"url": "http://example.com"}))
    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(cfg), "--format", "xml"])
    assert result.exit_code != 0
    assert "xml" in result.output.lower() or "format" in result.output.lower()
