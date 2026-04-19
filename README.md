# ⚡🔄🛂 Gauntlet

Gauntlet is a two-role adversarial MCP server that infers software correctness by observing how code behaves under sustained, targeted attack. It's designed as quality control for a dark-factory environment - where code is written by bots and verified by attack.

The name comes from "running the gauntlet": a challenge where you must survive a sustained barrage from all sides. Here, the host Claude Code agent drives the system under test through escalating tiers of adversarial pressure until hidden failure modes become detectable - then gates promotion on whether any signal came through.

AI-written code can look correct - following conventions, passing linting, reading plausibly - while hiding behavioral failures that only surface under real use. Traditional tests don't catch this because the same agent that wrote the code also wrote the tests, sharing the same blind spots. Gauntlet is built for this: the host's Attacker context assumes the code is broken and generates plans the code author never considered, and the `blockers` in each Weapon are never loaded into that context, preserving a real train/test split that prevents the agent from inadvertently writing code that passes by knowing what the tests check.

> An **Attacker** uses a **Weapon** aimed at a **Target** to generate **Plans**. Gauntlet's Drone executes those Plans as a **User**. An **Inspector** watches and surfaces **Findings**. Hidden **Vitals** - externally observable truths about expected system behavior - are checked independently to produce a **Clearance**.

## Operating model

Gauntlet runs **exclusively as an MCP server inside Claude Code**. There is no CLI, no remote CI mode, and no standalone invocation path. The host Claude Code agent plays the Attacker and Inspector roles itself - two prompt contexts it drives in its own loop - and calls Gauntlet's MCP tools for the deterministic pieces: config loading, plan execution against the SUT, weapon assessment, and risk-report assembly.

Because Gauntlet runs inside a Claude Code session, no Anthropic credentials are needed - the host already has auth.

## Install and register

```bash
uv add gauntlet     # or: pip install gauntlet
claude mcp add gauntlet -- uv run gauntlet-mcp
```

Once registered, Claude Code will expose the `gauntlet` MCP server to any session in that project. Confirm it is discovered with `/mcp` inside Claude Code.

## MCP tools

| Tool | Purpose | Use in host role |
|---|---|---|
| `list_weapons(weapons_path, arsenal_path)` | List attacker-safe `WeaponBrief`s (no blockers) | Attacker |
| `get_weapon(weapon_id, ...)` | Return full weapon including blockers | HoldoutEvaluator only |
| `list_targets(targets_path, openapi_path)` | List configured `Target` surfaces | Attacker |
| `execute_plan(url, plan, users_path)` | Deterministically run a `Plan` against the SUT | Attacker + HoldoutEvaluator |
| `assess_weapon(weapon_id, target, ...)` | Preflight quality check on a weapon | Orchestrator |
| `assemble_run_report(iterations, holdout_results, clearance_threshold)` | Build final `RiskReport` + `Clearance` | Orchestrator |
| `default_iteration_specs()` | Return the reference 4-stage escalation ladder | Orchestrator |

The train/test split is maintained by host-side prompt discipline: only `list_weapons` is safe to read in the Attacker context. Pulling full weapons via `get_weapon` inside the Attacker context collapses the split and invalidates the run.

## Project config directory

Gauntlet reads configuration from a `.gauntlet/` directory at the root of the project:

```
your-project/
├── .gauntlet/
│   ├── weapons/           # one YAML file per Weapon
│   │   ├── task_ownership.yaml
│   │   └── task_read_isolation.yaml
│   ├── targets/           # one YAML file per Target
│   │   └── task_endpoints.yaml
│   └── users.yaml         # optional: per-user auth credentials
└── ...
```

Every MCP tool that reads config accepts an override path argument.

### Weapons

A Weapon defines a reusable attack strategy. The `blockers` are the Weapon's **Vitals** - externally observable truths about expected system behavior - never surfaced in the Attacker context, preserving the train/test separation.

```yaml
# .gauntlet/weapons/task_ownership.yaml
title: Users cannot modify each other's tasks
description: >
  The task API must enforce resource ownership. A user who did not create
  a task must not be able to modify or delete it.
blockers:
  - A PATCH request by a non-owner is rejected with 403
  - The task body is unchanged after an unauthorized PATCH attempt
  - A GET by the owner after an unauthorized PATCH returns the original data
```

### Targets

A Target defines the API surface a Weapon is tested against. One target per YAML file.

```yaml
# .gauntlet/targets/task_endpoints.yaml
title: Task ownership endpoints
endpoints:
  - POST /tasks
  - PATCH /tasks/{id}
  - GET /tasks/{id}
```

### User authentication

Create `.gauntlet/users.yaml` to provide per-user credentials. Secret values are never stored in the file - each entry names an environment variable that holds the actual credential. Users omitted from the file fall back to the default `X-User: <name>` header.

```yaml
# .gauntlet/users.yaml
users:
  alice:
    type: bearer
    token_env: ALICE_TOKEN
  bob:
    type: api_key
    header: X-API-Key
    key_env: BOB_API_KEY
```

Supported authentication types:

| Type | Fields | Header sent |
|---|---|---|
| `bearer` | `token_env` | `Authorization: Bearer <$token_env>` |
| `api_key` | `header`, `key_env` | `<header>: <$key_env>` |

### Arsenals

An Arsenal is a named collection of weapons bundled in a single YAML file - useful for selecting an entire attack class (authorization, input validation, OWASP top-10) as a unit.

```yaml
# .gauntlet/authz_arsenal.yaml
name: authz
description: Authorization and ownership enforcement weapons
weapons:
  - id: identity_swap
    title: Users cannot access or modify each other's resources
    description: >
      The API must enforce resource ownership at every endpoint.
    blockers:
      - A write request by a non-owner is rejected with 403 or 404
      - A read request by a non-owner returns 403 or 404
```

Pass `arsenal_path` to `list_weapons` / `get_weapon` / `assess_weapon` to load from an arsenal file.

## Core Model

Gauntlet treats code change correctness as a problem of behavioral observation while under attack.

- Code is assumed untrusted, potentially written by a human but designed to be written by a bot
- Tests are generated dynamically by the host agent
- Confidence emerges from what survives adversarial probing

It asks: "How hard did we try to break this, and what happened when we did?"

## The Two Roles

### The Attacker

Explores the execution space.

- Constructs plausible, production-like plans
- Simulates how the system will actually be used (and misused)
- Explores workflows, edge cases, and state transitions
- Adapts based on what has already been tested

The Attacker is not trying to prove correctness. It is trying to create situations where correctness might fail.

### The Inspector

Applies intelligent pressure.

- Analyzes execution results for weaknesses
- Identifies suspicious passes and untested assumptions
- Forms hypotheses about hidden failure modes
- Forces the next round of plans toward likely breakpoints

The Inspector assumes "This system is broken. I just haven't proven it yet."

### Dynamic Between Them

- The Attacker explores
- The Inspector sharpens
- Execution grounds both

Together, they perform a form of guided adversarial search over the space of possible failures.

## What Makes This Different

Gauntlet is not:

- a test runner
- a code reviewer
- a fuzzing tool

It is an adversarial inference engine for software correctness.

It combines:

- dynamic plan generation (like red teaming)
- execution grounding (like CI)
- adversarial refinement (like security testing)

## Prior Art

These projects occupy the same space - adversarial testing of running services.

### [RESTler](https://github.com/microsoft/restler-fuzzer)

Stateful REST API fuzzer from Microsoft Research. RESTler generates and executes sequences of HTTP requests against a live service, inferring producer-consumer dependencies between endpoints from the OpenAPI spec to explore deep service states.

Shared ground: attacks a **running HTTP server** with **multi-step request sequences**, finds bugs that only manifest through specific request orderings, and checks for both security and reliability failures.

Architectural divergence: RESTler uses grammar-based fuzzing derived from the OpenAPI spec, not LLM reasoning. Validation is hardcoded checkers (status codes, schema conformance), not an Inspector that reasons about what looks suspicious. There is no train/test split - all validation rules are visible to the generation logic. Output is boolean pass/fail per sequence, not a probabilistic confidence score.

### [Schemathesis](https://github.com/schemathesis/schemathesis)

Property-based API testing built on the Hypothesis framework. Generates thousands of test cases from OpenAPI/GraphQL schemas and executes them against a live API to find crashes, schema violations, and stateful workflow bugs.

Shared ground: tests a **live running API**, supports **stateful multi-step workflows** where earlier requests create resources consumed by later ones, and is deliberately **adversarial** - generating edge cases, boundary conditions, and invalid inputs to break the API.

Architectural divergence: generation is algorithmic (property-based testing), not LLM-driven. There is no Attacker/Inspector separation - generation and validation are unified. No hidden blockers or train/test split. Results are deterministic pass/fail, not probabilistic confidence.

### [ToolFuzz](https://github.com/eth-sri/ToolFuzz)

LLM-powered fuzzer from ETH Zurich that generates natural-language test prompts and executes them against LLM agent tools, detecting both runtime crashes and semantic correctness failures.

Shared ground: **uses LLMs to generate adversarial inputs** and has **separate generation and evaluation phases** - prompts are generated, executed against the target, and then an LLM judges whether outputs are semantically correct. This is the closest architectural parallel to the host's Attacker/Inspector roles plus Gauntlet's deterministic execution layer.

Architectural divergence: targets LLM agent tools (LangChain, Composio) rather than arbitrary HTTP APIs. No hidden blockers or train/test split - the evaluator sees all context. Attacks are individual prompts, not multi-step chained API call sequences. No probabilistic confidence scoring.
