from __future__ import annotations

import argparse
import sys
from urllib.parse import urlparse

import yaml

from .executor import DeterministicLocalExecutor, HttpExecutor
from .loop import FluxGateRunner
from .roles import DemoAdversary, DemoOperator


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flux-gate",
        description=(
            "Adversarial inference engine for software correctness. "
            "Runs a two-agent loop against a locally-running HTTP API and "
            "outputs a risk report."
        ),
    )
    parser.add_argument(
        "url",
        help="Base URL of the running API (e.g. http://localhost:8000)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Human-readable name for the system under test (default: URL hostname)",
    )
    parser.add_argument(
        "--env",
        default="local",
        help="Environment label included in the report (default: local)",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    name: str = args.name or urlparse(args.url).netloc or args.url

    executor = DeterministicLocalExecutor(HttpExecutor(args.url))
    runner = FluxGateRunner(
        executor=executor,
        operator=DemoOperator(),
        adversary=DemoAdversary(),
        system_under_test=name,
        environment=args.env,
    )

    try:
        run = runner.run()
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(yaml.dump(run.model_dump(), sort_keys=False, allow_unicode=True))
