# Architecture

## Module map

```
flux_gate/
├── models.py    # all Pydantic data models — the shared vocabulary
├── auth.py      # actor authentication config (BearerAuth, ApiKeyAuth, ActorsConfig)
├── roles.py     # Operator, Adversary, HoldoutEvaluator, GuardAssessor protocols + demo impls
├── executor.py  # SystemUnderTest protocol + HttpExecutor + InMemoryTaskAPI + DeterministicLocalExecutor
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
├── [preflight] GuardAssessor.assess(guard) — if assessor present
│     └── returns GuardAssessment; blocked → short-circuit
│
├── for each IterationSpec (4 total):
│   ├── Operator.generate_scenarios(spec, previous records)
│   │     └── returns []Scenario
│   │
│   ├── DeterministicLocalExecutor.run_scenario(scenario) × N
│   │     ├── resolves path templates from prior step responses
│   │     ├── calls SystemUnderTest.send(actor, request)
│   │     └── evaluates assertions → []AssertionResult
│   │         returns ExecutionResult
│   │
│   ├── Adversary.analyze(spec, execution_results)
│   │     └── returns []Finding
│   │
│   └── appends IterationRecord to records
│
├── [holdout] HoldoutEvaluator or NaturalLanguageHoldoutEvaluator
│     └── evaluates guard acceptance scenarios (Operator never sees these)
│
└── _build_risk_report(records)
      ├── aggregates findings across all iterations
      ├── derives coverage from all executed steps
      ├── computes confidence_score (1 - avg finding confidence)
      ├── derives risk_level from highest finding severity
      ├── evaluates merge gate against gate_threshold
      └── returns RiskReport
```

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
