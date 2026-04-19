# TODO

Bounded follow-ups. Anything here is contingent on a real consumer asking for it; "might be useful" doesn't promote a TODO into work.

## Wire up `ReplayBundle` so attack patterns are deterministically reproducible

`Finding` carries an optional `replay_bundle: ReplayBundle | None` field, but nothing populates it today. The model exists; the wiring doesn't.

Attack patterns are supposed to be reproducible deterministic steps — that's the difference between Gauntlet's findings and a manual bug report. Without a populated `ReplayBundle`, the only reproduction path is for a human to read `evidence` + `reproduction_steps` (free-form English) and manually re-derive the request sequence. That defeats the point.

What needs to happen:

- The Inspector subagent should populate `replay_bundle` on every `Finding` it emits, copying the `ReplayStep`s from the `ExecutionResult.steps` that produced the finding.
- The Inspector's [`SKILL`-style prose](agents/gauntlet-inspector.md) should mandate it (currently silent on the field).
- A schema-level enforcement at the buffer boundary, similar to the `violated_blocker is None` check, would be ideal — `record_iteration` could reject findings without a `replay_bundle`. Risk: this adds a hard requirement that may surprise consumers; consider a softer first pass (warning, not rejection) until the discipline is bedded in.
- Once populated, add a `replay_finding(finding_id_or_run_id_pair, url, user_headers)` MCP tool that takes a stored finding and re-executes its `ReplayBundle` against the SUT — useful for "did the fix actually work" loops.

Open questions:

- Path-template handling: `ReplayBundle.steps` carry raw `HttpRequest`s. Dynamic IDs (`{task_id}` resolved from a prior POST response) need either to be re-resolved at replay time or baked in at capture time. The current Drone resolves them at run time; the replay bundle should probably do the same.
- What identifies a finding for replay? `(weapon_id, issue, run_id)`? A separate finding id?

## In-flight structured logging

Gauntlet emits no observability today — no per-tool latency, no per-run timings, no error counts. The host has to wrap MCP calls itself if it wants any of that. Reasonable next step: structured logs to stderr via Python's `logging` module with a JSON formatter. The host pipes stderr wherever it wants (terminal, file, log aggregator). One log line per MCP tool call, with `tool`, `run_id`, `weapon_id`, `duration_ms`, and `status` fields.

Specifically NOT in scope for the first pass:
- A summary file written at end-of-run. Add this only if a consumer asks for it.
- A separate per-call timings JSONL alongside the buffers. Same reason.
- OpenTelemetry / tracing. The host owns its own observability stack; Gauntlet shouldn't pick a vendor.

The first pass is "stderr lines a human or `jq` can read." Anything beyond that needs a real consumer asking for it.

## Across-iteration plan mutation

Today the Attacker subagent re-derives plans from scratch each iteration by re-prompting against the iteration buffer. A deterministic Python mutator could take a plan that landed in iteration N and produce variants for iteration N+1 (drop a field, swap users, change expected status). Wins: determinism, no LLM tokens for the mutation step. Losses: re-introduces a Python "intelligence" layer that competes with the Attacker subagent, for a marginal token saving since each iteration only generates 2-4 plans.

**Defer until at least one production loop has battle-tested the in-prompt approach.** If the Attacker subagent's regenerate-from-scratch loop turns out to under-explore (the same baseline plan keeps getting repeated, edge cases never surface), revisit. Until then, don't.

If revisited:
- Mutator reads only what the Attacker has already seen (`read_iteration_records`); no train/test split risk.
- Lives behind a new MCP tool the Attacker can call, not as a hidden replacement for in-prompt generation.
- Stays within a single run. Cross-run plan persistence is a separate question (would re-introduce a `PlanStore`-shaped thing, which we deliberately deleted).

## Cross-run failure correlation

Each Gauntlet run is fully ephemeral today — `.gauntlet/runs/<run_id>/` is wiped between runs in practice, and there's no cross-run aggregator. If a project re-runs Gauntlet across days/weeks of iterations, knowing "this same `confirmed_failure` showed up in 3 of the last 5 runs" is genuinely useful signal.

Out of scope until a real consumer asks for it. Shape would be a re-introduced `FindingsStore` keyed by `weapon_id`, plus an MCP tool like `recurring_failures(weapon_id, lookback=5)`. Both were deleted; both could come back if the use case materializes.

