# 13 — Testing

## 1. Test pyramid, mapped to this system's actual risk

The guiding principle: put the most testing effort where a wrong answer is cheapest to have been wrong about and fastest to check, and treat "the LLM behaved unpredictably" as a class of event that must be *contained*, not a class of event that can be eliminated by testing the LLM itself.

## 2. Unit tests

- **`compute_pmv`**: golden-value tests against known Fanger/ISO 7730 reference points (published example input/output combinations for the PMV-PPD model) — this is the one place in the system where "the published reference table says X, our function must return X" is a meaningful, exact test, precisely because the underlying model is a fixed analytical formula, not something with expected variance.
- **`validate_action`**: property-based testing — generate a large number of random candidate actions (including deliberately out-of-bound ones) and assert the pass/fail outcome always matches the config-loaded bounds, for every actuator in the allow-list, with no exceptions. This is the single most important unit-test target in the whole system, because SR-1 through SR-4 (`01_Requirements.md`) rest entirely on this function being correct.
- **`propose_setpoints`**: unit tests confirm it never returns a candidate outside the hard bounds (even before `validate_action` double-checks it) and that it degrades to the documented `infeasible` result rather than silently clamping or guessing when no valid candidate exists.
- **Config schema validation**: tests confirm a config referencing a non-existent actuator, or missing a required LLM endpoint in `agent` mode, fails at load time with a clear error — not three hundred timesteps into a run.
- **Idempotency logic** (`apply_setpoints`, `log_decision`, `raise_incident`): unit tests directly exercise the "same `cycle_id`, same action twice" and "same `cycle_id`, different action" cases against the expectations in `09_MCP_Architecture.md` §2.7.

## 3. Integration tests

- **Agent Orchestrator + MCP tools, EnergyPlus mocked out entirely, LLM replaced with a scripted/deterministic stub** that returns a fixed sequence of tool calls. This tests the *orchestration logic* (does the loop call tools in the right order, does it respect the tool-call budget, does it escalate correctly on a scripted validation failure) without paying for real simulation time or real inference latency — the classic test-pyramid argument for why this layer exists separately from full end-to-end tests.
- **Bridge + a short EnergyPlus run, agent mocked out** (a fixed, scripted `on_decision_cycle` response): tests that sensor reads, PMV computation, and actuator commits actually round-trip correctly against a real EnergyPlus process, isolating whether a bug is in the simulation coupling or in the agent logic.
- **MCP server contract tests**: for every tool in `09_MCP_Architecture.md`, a test asserts the declared input/output schema is actually what the server accepts/returns, and that the documented error shapes (`isError` cases) are actually produced under the documented conditions.

## 4. Simulation-level tests

- **Short design-day runs** (1–2 simulated days) as the default CI-speed test: fast enough to run on every change, long enough to exercise a handful of real decision cycles end-to-end (Bridge, real EnergyPlus, real MCP server, real LLM if available, or the deterministic stub otherwise).
- **Full representative-day runs** (the actual demo configuration, per `01_Requirements.md` PR-3) as a slower, less-frequent (nightly or pre-demo) test tier.
- **Full-annual baseline-only run** (no AI loop, no latency concern) as a periodic sanity check that the underlying building model itself behaves reasonably across a full year, independent of anything this project adds.

## 5. Fault injection

Each failure condition enumerated in `01_Requirements.md` §10 gets a dedicated test that deliberately induces it and asserts the *documented* graceful-degradation behavior is what actually happens — not merely that the system "doesn't crash," but that it reaches the specific fallback state this spec claims it will:

| Injected fault | Expected observed behavior |
|---|---|
| LLM server unreachable | Fallback controller engages within the cycle timeout; `raise_incident` fired; simulation continues; RR-3's degraded-mode reconnection attempts observed in logs |
| Malformed LLM tool call | Protocol-level error surfaces to orchestrator (not a crash); one in-cycle retry with the error fed back; escalation if still malformed |
| Semantically out-of-bound but well-formed action | `validate_action` returns `valid: false` with a specific reason; agent gets one revision attempt within budget; escalation if still invalid |
| LLM call exceeds latency budget | Cycle-level timeout fires (not just the LLM-call-level timeout); fallback engages; no simulation stall |
| EnergyPlus recoverable severe error | Run continues; event tagged `error_recovery`; no data loss |
| EnergyPlus fatal error | Run terminates gracefully; buffered telemetry flushed; `RunSummary.status = "incomplete"`, not silently marked complete |
| Database write failure | Bounded async buffer applies documented backpressure (drop lowest-priority telemetry first, never drop `DecisionLog`/`Incident`); simulation unaffected |
| Concurrent `apply_setpoints` for the same `cycle_id` | Second call is a no-op (matching action) or rejected (mismatched action) — never a double-write |
| Process killed and restarted mid-run | New `run_id` on restart; no double-counted records against the killed run's partial data |
| Config references an actuator absent from the loaded `.idf` | Startup validation fails before `run_energyplus` is called |

## 6. Stress testing

- Rapid-fire decision cycles (artificially short cadence in a test configuration) to confirm the tool-call budget and cycle timeout hold up under load, and that the async logging buffer's backpressure behavior (§3 of `04_Dataflow.md`) engages correctly rather than growing unbounded.
- Long-run memory growth: confirm the rolling-window + periodic-reflection memory design (`08_LLM_and_Agent_System.md` §3) actually keeps prompt size bounded over a multi-day simulated run, rather than silently growing until it hits a context-length error.

## 7. Recovery testing

- Kill-and-restart at several points in a run (mid-warmup, mid-run-period, immediately after a commit) and confirm Storage's `run_id`-keyed schema produces no double-counted or corrupted records, per RR-5.
- Confirm a restarted run's `RunSummary` for the *previous, killed* attempt is correctly marked incomplete and excluded from Analytics comparisons rather than silently averaged in.

## 8. Hallucination prevention — tested as a property of the *guardrail*, not a property of the model

This is worth stating precisely, because it's easy to promise something untestable: **it is not possible to test or prove that an LLM will never propose an unsafe action** — that would require bounding the behavior of a system this project does not control the training of. What **is** testable, and is exactly what `13_Testing.md` actually verifies, is that **the deterministic validator catches every out-of-bound action regardless of why the LLM proposed it**. Concretely:

- Adversarial-input fuzzing of `validate_action` (§2 above) with a very large number of random and boundary-case candidates, asserting 100% correct pass/fail against the configured bounds, with no false "pass."
- End-to-end tests using a deliberately misbehaving LLM stub (scripted to propose out-of-bound, malformed, or contradictory actions on purpose) confirming that **no** such action ever results in an actual `set_actuator_value` call reaching EnergyPlus — the assertion is on the actuator write, the one place where a hallucination would actually matter, not on the model's text output.
- This reframing — "prove the gate works," not "prove the model behaves" — is the honest, defensible version of a hallucination-prevention test plan, and is the version this project actually commits to.

## 9. Regression testing

- **Golden-run comparison**: a fixed `.idf`/`.epw`/config combination, with LLM sampling set to its most deterministic setting where the serving stack supports it, is expected to produce energy and comfort metrics within a small tolerance band of the last known-good run. A metric drifting outside that band on an otherwise-unchanged codebase is treated as a signal to investigate (a prompt change, a model swap, a dependency upgrade), not ignored.
- **Non-determinism is explicitly not conflated with regression**: LLM sampling variance (when not pinned to a deterministic setting) is expected and is not, by itself, treated as a test failure — the regression suite is designed around the deterministic-sampling configuration specifically so that "did behavior actually change" and "did the model happen to sample differently this time" are not confused with each other.
