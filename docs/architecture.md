# Architecture

## Module map

```
flux_gate/
├── models.py    # all Pydantic data models — the shared vocabulary
├── auth.py      # actor authentication config (BearerAuth, ApiKeyAuth, ActorsConfig)
├── roles.py     # Operator, Adversary, HoldoutVitals, WeaponAssessor protocols + demo impls
├── executor.py  # Api protocol + HttpExecutor + InMemoryTaskAPI + DeterministicLocalExecutor
├── llm.py       # LLMOperator and LLMAdversary backed by OpenAI or Anthropic
├── loop.py      # FluxGateRunner orchestration + risk report assembly
└── cli.py       # Click entry point — reads env vars, loads config, runs FluxGateRunner
```

Nothing imports from `loop.py` or `cli.py` except `__init__.py`. Dependency order is:

```
models  ←  auth
models  ←  roles
models  ←  executor
models + roles + executor  ←  loop
models + auth + roles + executor + llm + loop  ←  cli
```

## Data flow

```
FluxGateRunner.run()
│
├── [preflight] WeaponAssessor.assess(weapon) — if assessor present
│     └── returns WeaponAssessment; blocked → short-circuit
│
├── for each IterationSpec (4 total):
│   ├── Operator.generate_scenarios(spec, previous records)
│   │     └── returns []Scenario
│   │
│   ├── DeterministicLocalExecutor.run_scenario(scenario) × N
│   │     ├── resolves path templates from prior step responses
│   │     ├── calls Api.send(actor, request)
│   │     └── evaluates assertions → []AssertionResult
│   │         returns ExecutionResult
│   │
│   ├── Adversary.analyze(spec, execution_results)
│   │     └── returns []Finding
│   │
│   └── appends IterationRecord to records
│
├── [holdout] HoldoutVitals or NaturalLanguageHoldoutVitals
│     └── evaluates weapon acceptance scenarios (Operator never sees these)
│
└── _build_risk_report(records)
      ├── aggregates findings across all iterations
      ├── derives coverage from all executed steps
      ├── computes confidence_score (1 - avg finding confidence)
      ├── derives risk_level from highest finding severity
      ├── evaluates merge gate against gate_threshold
      └── returns RiskReport
```

## Deterministic vs non-deterministic segments

The system is split into a **deterministic core** and **non-deterministic edges**.

**Deterministic (no LLM, no network):**

- `InMemoryTaskAPI` — in-memory REST API; pure dict operations, always same output for same input. Ships with the library as a working example SUT.
- `DeterministicLocalExecutor` — resolves path templates, calls the SUT, evaluates assertions. Pure Python.
- Assertion evaluation and risk report assembly — branching logic, set unions, averages, threshold arithmetic. Fully reproducible.
- `Demo*` classes — hardcoded or regex-based implementations of each Protocol. Shipped with the library so users can run the full loop without API keys.

**Non-deterministic (LLM or network):**

- `LLMOperator` / `LLMAdversary` (`llm.py`) — call an LLM to generate scenarios and analyze findings. Output varies per call.
- `HttpExecutor` — sends real HTTP requests; outcome depends on network and the running server.

The `Demo*` classes are reference implementations of each Protocol in `roles.py`. They exist so that `FluxGateRunner` can be exercised end-to-end in tests and examples without any external dependencies. The `LLM*` classes are the production counterparts.

## Design decisions

**Why Pydantic?** All interchange objects are `BaseModel` subclasses with
`extra="forbid"`. This catches schema drift early and makes JSON
serialization/deserialization free.

**Why 4 fixed iterations?** v0 trades flexibility for predictability. The four
goals (baseline → boundary → adversarial → targeted) form a natural escalation
ladder that works well for demo purposes. Future versions will make this
configurable.

**Why Protocols instead of ABCs?** Structural subtyping lets callers pass any
object that has the right methods without importing from `flux_gate`. This keeps
the integration surface small and avoids inheritance coupling.

**Why separate auth.py?** Actor credentials involve secret resolution from env
vars. Isolating this in `auth.py` keeps the rest of the codebase free of
secret-handling logic and makes the boundary clear.

**Why LLM providers are configurable per-role?** The Operator and Adversary
can use different providers (e.g., GPT-4 vs Claude) so users can mix strengths
or reduce cost.
