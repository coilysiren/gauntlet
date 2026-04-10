import yaml

from flux_gate import (
    DemoAdversary,
    DemoOperator,
    DeterministicLocalExecutor,
    FluxGateRunner,
    InMemoryTaskAPI,
)


def main() -> None:
    runner = FluxGateRunner(
        executor=DeterministicLocalExecutor(InMemoryTaskAPI()),
        operator=DemoOperator(),
        adversary=DemoAdversary(),
    )
    run = runner.run()
    print(yaml.dump(run.model_dump(), sort_keys=False, allow_unicode=True))


if __name__ == "__main__":
    main()
