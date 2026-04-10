import subprocess

import pytest


@pytest.mark.docker
def test_demo_service_runs() -> None:
    """flux-gate CLI runs against the demo API container and exits cleanly."""
    result = subprocess.run(
        ["docker", "compose", "run", "--rm", "demo"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "risk_report" in result.stdout


@pytest.mark.docker
def test_test_service_passes() -> None:
    """Unit tests pass inside the container."""
    result = subprocess.run(
        ["docker", "compose", "run", "--rm", "test"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
