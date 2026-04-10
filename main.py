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
    print(run.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
