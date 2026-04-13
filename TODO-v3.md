1. **OpenAPI-driven plan generation** (RESTler) — Auto-generate attack sequences directly from the OpenAPI spec by inferring producer-consumer dependencies between endpoints. Gauntlet currently relies on the LLM to figure out request chaining from the weapon/target definitions.

2. **Multiple exploration strategies** (RESTler) — BFS (systematic, exhaustive), random-walk (infinite random exploration), directed-smoke-test (shortest path to each endpoint). Gauntlet has a single fixed 4-iteration ladder.

3. **Continuous fuzzing mode** (Schemathesis) — Run indefinitely until timeout or first failure, no predefined iteration count. Useful for overnight or pipeline runs.

8. **Negative test mode** (Schemathesis) — Deliberately generate schema-invalid inputs (wrong types, missing required fields, out-of-range values) to verify the API rejects them properly. Gauntlet's Attacker generates plausible plans, not deliberately malformed ones.

9. **Positive acceptance checking** (Schemathesis) — After sending schema-valid data, verify the API actually accepts it (2xx). Detects over-strict validation.

10. **Taint-based constraint violation** (ToolFuzz) — Extract parameter constraints from schema/code and systematically generate values that violate each constraint individually. More targeted than random fuzzing.

11. **Automatic input shrinking** (Schemathesis) — When a failing input is found, minimize it to the smallest input that still triggers the failure. Makes reproductions cleaner.

12. **Targeted generation toward a metric** (Schemathesis) — Steer input generation toward maximizing a custom metric (response time, response size, error frequency). Finds performance bottlenecks and DoS vectors faster than random generation.

15. **Use-after-free check** (RESTler, Schemathesis) — After a successful DELETE, re-request the deleted resource. If it returns 200, the resource wasn't actually deleted.

16. **Resource hierarchy check** (RESTler) — After creating a child under parent A, request that child under parent B. If it succeeds, access control on the parent-child relationship is broken.

17. **Leakage rule check** (RESTler) — After a failed creation request (4xx), try to access the resource anyway. If it exists, the API partially created it before returning an error.

18. **Auth enforcement check** (Schemathesis) — For endpoints declaring security requirements, send requests with no credentials and with invalid credentials. If they succeed, auth is not actually enforced.

19. **Schema conformance validation** (Schemathesis) — Validate every response body against its declared JSON Schema. Catches type errors, missing required fields, format violations.

20. **Status code conformance** (Schemathesis) — Verify every response status code appears in the schema's documented responses for that operation. Catches undocumented error codes.

23. **Bug taxonomy by root cause** (ToolFuzz) — Classify each bug as under-specified, over-specified, or ill-specified rather than just by severity. Helps prioritize fixes.

24. **Custom bug code rules** (RESTler) — Configurable lists of status codes to treat as bugs (beyond 5xx) or to treat as non-bugs. Gauntlet's severity classification is LLM-driven with no hard rules.

25. **Replay files** (RESTler) — Each bug gets a standalone file containing the exact HTTP request sequence that triggered it, re-executable with a single command.

27. **Automatic reproduction attempts** (RESTler) — Immediately re-run the failing sequence after discovery and record whether it reproduces. Separates flaky from reliable failures.

28. **Bug deduplication by shortest reproducer** (RESTler) — When a bug is found via a long sequence, check if a shorter sequence ending in the same request already exists. Prefer the shorter one.

30. **Output sanitization** (Schemathesis) — Automatically mask secrets/tokens in all output and reports. Configurable patterns and replacement strings.

31. **Dual-format reporting** (ToolFuzz) — HTML for human review, JSON for CI/programmatic consumption. Side by side.

32. **Coverage tracking per-request** (RESTler) — Per-endpoint status (valid/invalid, why it failed, sample request/response) in structured JSON. Gauntlet tracks coverage as a flat set of endpoint strings.

33. **Schema-level coverage** (Schemathesis) — Track which JSON Schema keywords (minLength, pattern, enum) were actually exercised during the run, not just which endpoints were hit.

34. **Warning-to-failure promotion** (Schemathesis) — Promote diagnostic warnings (missing auth config, validation mismatches) to hard CI failures. Gauntlet has no warning system.

41. **Hooks/lifecycle system** (Schemathesis) — before_call, after_call, filter/map/flatmap on every request component. Allows injecting custom logic at every stage without forking.

42. **Custom checks as plugins** (Schemathesis, RESTler) — Register a function or class that runs against every response, alongside built-in checks. Gauntlet's Inspector is monolithic.

43. **Documentation auto-fix pipeline** (ToolFuzz) — After discovering bugs, an LLM rewrites the documentation/spec to eliminate the specification errors that caused them.
