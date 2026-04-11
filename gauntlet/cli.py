from __future__ import annotations

import os
import sys
from pathlib import Path

import click
import yaml

from .auth import UsersConfig, to_user_headers
from .executor import Drone, HttpExecutor
from .llm import create_attacker, create_inspector
from .loop import GauntletRunner
from .models import Target, Weapon
from .roles import DemoWeaponAssessor

_ENV_ATTACKER_TYPE = "GAUNTLET_ATTACKER_TYPE"
_ENV_ATTACKER_KEY = "GAUNTLET_ATTACKER_KEY"
_ENV_INSPECTOR_TYPE = "GAUNTLET_INSPECTOR_TYPE"
_ENV_INSPECTOR_KEY = "GAUNTLET_INSPECTOR_KEY"


def _load_weapons(spec: str) -> list[Weapon]:
    """Return weapons from a single YAML file or all *.yaml files in a directory."""
    path = Path(spec)
    if not path.exists():
        return []
    if path.is_dir():
        return [Weapon(**yaml.safe_load(f.read_text())) for f in sorted(path.glob("*.yaml"))]
    return [Weapon(**yaml.safe_load(path.read_text()))]


def _load_targets(spec: str) -> list[Target]:
    """Return targets from a single YAML file or all *.yaml files in a directory."""
    path = Path(spec)
    if not path.exists():
        return []
    if path.is_dir():
        return [Target(**yaml.safe_load(f.read_text())) for f in sorted(path.glob("*.yaml"))]
    return [Target(**yaml.safe_load(path.read_text()))]


@click.command(
    help=(
        "Adversarial inference engine for software correctness. "
        "Runs a two-agent LLM loop against a locally-running HTTP API and "
        "outputs a risk report."
    )
)
@click.argument("url")
@click.option(
    "--weapon",
    default=".gauntlet/weapons",
    metavar="FILE_OR_DIR",
    show_default=True,
    help="Path to a Weapon YAML file, or a directory of YAML files (one weapon per file).",
)
@click.option(
    "--target",
    default=".gauntlet/targets",
    metavar="FILE_OR_DIR",
    show_default=True,
    help="Path to a Target YAML file, or a directory of YAML files (one target per file).",
)
@click.option(
    "--users",
    default=".gauntlet/users.yaml",
    metavar="FILE",
    show_default=True,
    help="Path to an users YAML file defining per-user authentication.",
)
@click.option(
    "--threshold",
    type=float,
    default=0.90,
    metavar="N",
    show_default=True,
    help="Holdout satisfaction score required to recommend merge.",
)
@click.option(
    "--fail-fast/--no-fail-fast",
    default=True,
    show_default=True,
    help="Stop after the first critical finding.",
)
def main(url: str, weapon: str, target: str, users: str, threshold: float, fail_fast: bool) -> None:
    operator_type = os.environ.get(_ENV_ATTACKER_TYPE, "")
    operator_key = os.environ.get(_ENV_ATTACKER_KEY, "")
    adversary_type = os.environ.get(_ENV_INSPECTOR_TYPE, "")
    adversary_key = os.environ.get(_ENV_INSPECTOR_KEY, "")

    missing = [
        name
        for name, val in [
            (_ENV_ATTACKER_TYPE, operator_type),
            (_ENV_ATTACKER_KEY, operator_key),
            (_ENV_INSPECTOR_TYPE, adversary_type),
            (_ENV_INSPECTOR_KEY, adversary_key),
        ]
        if not val
    ]
    if missing:
        click.echo(
            f"error: missing required environment variables: {', '.join(missing)}\n"
            f"\n"
            f"Set them before running flux-gate:\n"
            f"  export {_ENV_ATTACKER_TYPE}=openai       # or: anthropic\n"
            f"  export {_ENV_ATTACKER_KEY}=sk-...\n"
            f"  export {_ENV_INSPECTOR_TYPE}=anthropic   # or: openai\n"
            f"  export {_ENV_INSPECTOR_KEY}=sk-ant-...",
            err=True,
        )
        sys.exit(1)

    weapons = _load_weapons(weapon)
    targets = _load_targets(target)

    user_headers: dict[str, dict[str, str]] = {}
    users_path = Path(users)
    if users_path.exists():
        user_headers = to_user_headers(UsersConfig(**yaml.safe_load(users_path.read_text())))

    attacker = create_attacker(operator_type, operator_key)
    inspector = create_inspector(adversary_type, adversary_key)
    executor = Drone(HttpExecutor(url, user_headers=user_headers))

    blocked = False
    for inv in weapons or [None]:  # type: ignore[list-item]
        for tgt in targets or [None]:  # type: ignore[list-item]
            runner = GauntletRunner(
                executor=executor,
                attacker=attacker,
                inspector=inspector,
                assessor=DemoWeaponAssessor() if inv else None,
                weapon=inv,
                target=tgt,
                gate_threshold=threshold,
                fail_fast_tier=0 if fail_fast else None,
            )

            try:
                run = runner.run()
            except Exception as exc:  # noqa: BLE001
                click.echo(f"error: {exc}", err=True)
                sys.exit(1)

            click.echo(yaml.dump(run.model_dump(), sort_keys=False, allow_unicode=True))

            gate = run.risk_report.clearance
            if gate and gate.recommendation == "block":
                click.echo(f"gate: BLOCKED — {gate.rationale}", err=True)
                blocked = True

    if blocked:
        sys.exit(1)
