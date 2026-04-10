# Flux Gate

Flux Gate is a two-agent adversarial loop that infers software correctness by observing how code behaves under sustained, targeted attack, and is designed as quality control for a dark factory environment.

## Installation

```bash
pip install flux-gate
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add flux-gate
```

## Quick start

```python
import yaml
from flux_gate import (
    DemoAdversary,
    DemoOperator,
    DeterministicLocalExecutor,
    FluxGateRunner,
    InMemoryTaskAPI,
)

runner = FluxGateRunner(
    executor=DeterministicLocalExecutor(InMemoryTaskAPI()),
    operator=DemoOperator(),
    adversary=DemoAdversary(),
)

run = runner.run()
print(yaml.dump(run.model_dump(), sort_keys=False, allow_unicode=True))
```

## Usage

### Bring your own system under test

Replace `InMemoryTaskAPI` with any object that implements `send(actor, request) -> HttpResponse`:

```python
import requests as http
from flux_gate import FluxGateRunner, DeterministicLocalExecutor, HttpRequest, HttpResponse

class LiveAPI:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def send(self, actor: str, request: HttpRequest) -> HttpResponse:
        resp = http.request(
            request.method,
            f"{self._base_url}{request.path}",
            json=request.body or None,
            headers={"X-Actor": actor},
        )
        return HttpResponse(status_code=resp.status_code, body=resp.json())
```

### Bring your own Operator and Adversary

Implement either protocol to plug in an LLM-backed agent:

```python
from flux_gate import (
    ExecutionResult,
    Finding,
    FluxGateRunner,
    IterationRecord,
    IterationSpec,
    Scenario,
)

class LLMOperator:
    def generate_scenarios(
        self, spec: IterationSpec, previous_iterations: list[IterationRecord]
    ) -> list[Scenario]:
        # call your LLM, parse response into Scenario objects
        ...

class LLMAdversary:
    def analyze(
        self, spec: IterationSpec, execution_results: list[ExecutionResult]
    ) -> list[Finding]:
        # call your LLM, parse response into Finding objects
        ...

runner = FluxGateRunner(
    executor=DeterministicLocalExecutor(LiveAPI("https://api.example.com")),
    operator=LLMOperator(),
    adversary=LLMAdversary(),
)
run = runner.run()
```

### Inspect the results

```python
run = runner.run()

# top-level risk verdict
print(run.risk_report.risk_level)        # "low" | "medium" | "high" | "critical"
print(run.risk_report.confidence_score)  # float 0.0–1.0
print(run.risk_report.confirmed_failures)

# per-iteration findings
for iteration in run.iterations:
    for finding in iteration.findings:
        print(finding.severity, finding.issue, finding.rationale)

# coverage
print(run.risk_report.coverage)          # ["GET /tasks/1", "PATCH /tasks/1", ...]
```

## Core Model

Flux Gate treats code change correctness as a problem of behavioral observation while under attack.

* Code is assumed to be untrusted, potentially written but a human - but designed to be written by a bot
* Tests are generated dynamically
* Confidence emerges from what survives adversarial probing

It asks: "How hard did we try to break this, and what happened when we did?"

## The Two Roles (Personified)

### The Operator (ChatGPT)

Explores the execution sphere

* Constructs plausible, production-like scenarios
* Simulates how the system will actually be used (and misused)
* Explores workflows, edge cases, and state transitions
* Adapts based on what has already been tested

The Operator is not trying to prove correctness, It is trying to create situations where correctness might fail.

### The Adversary (Claude)

Applies intelligent pressure

* Analyzes execution results for weaknesses
* Identifies suspicious passes and untested assumptions
* Forms hypotheses about hidden failure modes
* Forces the next round of scenarios toward likely breakpoints

The Adversary assumes "This system is broken. I just haven’t proven it yet."

### Dynamic Between Them

* The Operator explores
* The Adversary sharpens
* Execution grounds both

Together, they perform a form of guided adversarial search over the space of possible failures

## Concrete Flow (v0, fixed 4 iterations)

```yaml
flux_gate_run:
  system_under_test: REST API
  environment: deterministic_local

  roles:
    operator: ChatGPT
    Adversary: Claude

  loop:
    iterations: 4

    iteration_1:
      goal: broad_baseline
      operator: generate diverse CRUD + lifecycle scenarios
      execute: run scenarios
      Adversary: identify anomalies and weak coverage

    iteration_2:
      goal: boundary_and_invariants
      operator: target edge cases, missing fields, schema drift
      execute: run refined scenarios
      Adversary: escalate invariant violations

    iteration_3:
      goal: adversarial_misuse
      operator: simulate auth violations, invalid transitions, cross-user access
      execute: run attack scenarios
      Adversary: identify security and logic failures

    iteration_4:
      goal: targeted_followup
      operator: focus only on suspicious areas
      execute: confirm and expand blast radius
      Adversary: finalize failure model

  output:
    confidence_score: probabilistic
    risk_profile:
      - confirmed_failures
      - suspicious_patterns
      - unexplored_surfaces
```

### Scenario Shape (Example)

```yaml
scenario:
  name: user_cannot_modify_other_users_task
  category: authz

  steps:
    - actor: userA
      request:
        method: POST
        path: /tasks
        body:
          title: "private task"

    - actor: userB
      request:
        method: PATCH
        path: /tasks/{id}
        body:
          completed: true

    - actor: userA
      request:
        method: GET
        path: /tasks/{id}

  assertions:
    - type: status_code
      expected: 403

    - type: invariant
      rule: task_not_modified_by_other_user
```

### Execution Output (Example)

```yaml
execution_result:
  scenario: user_cannot_modify_other_users_task

  steps:
    - step: 1
      status: 201

    - step: 2
      status: 200   # suspicious

    - step: 3
      status: 200
      body:
        completed: true

  assertions:
    - name: unauthorized_patch_blocked
      result: fail
```

### Adversary Finding (Example)

```yaml
finding:
  issue: unauthorized_cross_user_modification
  severity: critical
  confidence: 0.94

  rationale: >
    userB successfully modified userA's resource.
    violation reproduced deterministically.

  next_targets:
    - ownership mutation
    - list endpoint visibility
```

### Final Output

```yaml
risk_report:
  confidence_score: 0.27
  risk_level: critical

  summary:
    - cross-user write vulnerability
    - destructive patch semantics
    - invariant violations under partial updates

  coverage:
    endpoints_tested:
      - POST /tasks
      - PATCH /tasks/{id}
      - GET /tasks/{id}

  conclusion: >
    system fails under moderate adversarial pressure.
    not safe for production deployment.
```

## What Makes This Different

Flux Gate is not:

* a test runner
* a code reviewer
* a fuzzing tool

It is an adversarial inference engine for software correctness

It combines:

* dynamic scenario generation (like red teaming)
* execution grounding (like CI)
* adversarial refinement (like security testing)
