# IMPLEMENTATION_CHECKLIST.md

Organized by `IMPLEMENTATION_ROADMAP.md` stage; each stage's checklist can become one GitHub milestone, with each `###` subsection a natural issue boundary. Every checkbox is independently verifiable — a reviewer can confirm it true or false without needing the rest of the list.

## Stage 1 — Foundation

### Repository & Environment
- [ ] Repository scaffold matches `REPOSITORY_STRUCTURE.md` exactly (all directories present, even if empty with `.gitkeep`)
- [ ] EnergyPlus version pinned and documented (matches ADR-002's version-pinning requirement)
- [ ] Python version pinned; dependency lockfile committed
- [ ] `eppy` installed and importable
- [ ] MCP SDK (Python) installed and importable

### Config
- [ ] `config/schema.py` defines every field named in `12_API_Design.md` §3
- [ ] `config/loader.py` loads a valid config successfully
- [ ] Loader rejects a config missing `llm.endpoint` when `run_mode: agent`
- [ ] Loader rejects a config referencing an actuator not resolvable against a loaded `.idf`
- [ ] `building_id` field present in schema from day one (SC-1), even with a single hard-coded value

### CI
- [ ] CI runs on push to any branch
- [ ] CI matrix includes both Linux and macOS runners (NFR-2)
- [ ] Lint step passes on an empty/scaffold codebase
- [ ] Unit test runner step configured (even with zero tests initially)

---

## Stage 2 — EnergyPlus Bridge

### Lifecycle
- [ ] `bridge/lifecycle.py` creates a new EnergyPlus state per run
- [ ] Bridge loads a real `.idf`/`.epw` pair and completes a short design-day run
- [ ] Warmup days correctly detected and decision-gating suppressed during them (EDGE-1)
- [ ] Design-day/sizing environments correctly distinguished from the run-period environment (EDGE-2)

### Handles
- [ ] Handle resolution occurs only after `api_data_fully_ready` returns true
- [ ] Handles are cached after first resolution, not re-resolved every timestep
- [ ] A config-declared actuator absent from the loaded `.idf` fails at startup, not mid-run (FC-10)

### Sensors
- [ ] `SensorSnapshot` populated every zone timestep with air temp, RH, meter values, current setpoints
- [ ] `compute_pmv` (from `comfort/`) invoked every timestep and result attached to the snapshot
- [ ] `current_time`/`zone_time_step_number` read from the exchange API each callback (no independent clock kept) (EDGE-4)

### Actuators
- [ ] A scripted actuator override is observably in effect on the next sensor read
- [ ] Actuator commit is idempotent by `cycle_id` (repeat commit, same value, is a no-op)
- [ ] Fallback path re-asserts last known-good value when no committed action exists for a cycle (FR-8, SR-4)

### idf_tools (parallel track)
- [ ] `idf_tools/ecm_sweep.py` generates at least one ECM variant from the baseline `.idf`
- [ ] Generated variant passes EnergyPlus's own IDD validation
- [ ] Generated variant runs successfully as an independent simulation

---

## Stage 3 — Storage

- [ ] `storage/schema.py` implements every table in `11_Database_Design.md` §6
- [ ] `storage/writer.py` accepts `SensorSnapshot` writes asynchronously (caller does not block)
- [ ] Backpressure drop-priority verified: telemetry dropped before `DecisionLog`/`Incident` under simulated slow-write conditions
- [ ] A full baseline (`run_mode: baseline`) run completes and populates all tables (parallel track — no agent required)
- [ ] Restart after a simulated kill does not duplicate rows for the same `run_id` (RR-5)
- [ ] Schema supports DuckDB; SQLite fallback verified to also work against the same schema

---

## Stage 4 — MCP Server

### Server & Registration
- [ ] MCP server starts over stdio transport
- [ ] Exactly ten tools registered — CI check confirms no more, no fewer (SR-3)
- [ ] Protocol version pinned at `initialize`; mismatch treated as startup failure

### Comfort, Optimizer, Validator
- [ ] `comfort/pmv.py` passes golden-value tests against published ISO 7730 reference points
- [ ] `optimizer/solver.py` never returns a candidate outside hard bounds
- [ ] `optimizer/solver.py` returns explicit `infeasible` rather than clamping when no valid candidate exists
- [ ] `validator/bounds.py` passes property-based fuzz testing with zero false "pass" results across a large randomized input set
- [ ] `apply_setpoints` independently re-validates server-side, even given a prior passing `validate_action` call (SR-2)

### Each tool, individually
- [ ] `get_zone_state`: schema, errors, timeout match `09_MCP_Architecture.md` §2.1 exactly
- [ ] `get_weather_forecast`: schema, errors, timeout match §2.2 exactly
- [ ] `get_utility_signal`: schema, errors, timeout match §2.3 exactly; `enabled: false` yields null values, not zeros
- [ ] `compute_pmv`: schema, errors, timeout match §2.4 exactly
- [ ] `propose_setpoints`: schema, errors, timeout match §2.5 exactly
- [ ] `validate_action`: schema, errors, timeout match §2.6 exactly
- [ ] `apply_setpoints`: idempotency by `cycle_id` verified (same `cycle_id` + same action = no-op; same `cycle_id` + different action = rejected)
- [ ] `get_history`: bounded query shapes only, no free-form query language; graceful `no_comparable_history` on cold start (EDGE-5)
- [ ] `log_decision`: async, non-blocking, never surfaces an error to the caller
- [ ] `raise_incident`: triggers fallback path at the Bridge level

---

## Stage 5 — LLM Agent

### Orchestrator
- [ ] Full ReAct loop (observe → reason → tool-call → propose → validate → commit/escalate) implemented per `05_Runtime_Execution.md` §4
- [ ] Tool-call budget enforced (default 6 per cycle)
- [ ] Cycle-level timeout enforced (wraps the whole loop, not just the LLM call) (PR-1, LR-1)
- [ ] Read-only tools retried up to 2x with backoff; `apply_setpoints` never blindly retried (RR-2)
- [ ] On validator rejection, failure reason fed back to the LLM for one in-cycle revision attempt before escalating

### Memory
- [ ] Rolling window holds only the last K cycles verbatim
- [ ] End-of-simulated-day reflection step regenerates the summary rather than appending to it
- [ ] `get_history` used for longer-horizon lookups instead of raw context stuffing (§2 of `15_Performance.md`)

### LLM Client
- [ ] Native or grammar-constrained tool calling enabled and verified against the chosen model/serving stack (ADR-008)
- [ ] Static system prompt + tool schemas kept as a stable prefix across calls (prefix-caching benefit measurable, LR-2)
- [ ] Deterministic-sampling configuration available for regression/demo runs (NFR-5)

### Monitoring
- [ ] Degraded mode triggers after 3 consecutive unreachable-LLM cycles (RR-3)
- [ ] Simulation continues under fallback controller during degraded mode, does not abort

### End-to-end
- [ ] A full representative-day run completes under agent control with real (non-scripted) LLM tool-calling traces
- [ ] Fallback invocation rate measured and logged (feeds acceptance criterion A3)

---

## Stage 6 — Analytics + Dashboard

- [ ] `get_run_summary` returns correct totals against a fixture dataset with known expected values
- [ ] `compare_runs` computes `pct_energy_reduction` and both runs' PMV-band compliance identically (same code path for both)
- [ ] `comfort_not_sacrificed` boolean correctly reflects agent-compliance ≥ baseline-compliance
- [ ] `get_decision_trace(cycle_id)` returns non-empty rationale and full trace for a real cycle
- [ ] Dashboard renders a full representative-day dataset within 5 seconds (PR-4)
- [ ] Dashboard has no write path to Storage, the Bridge, or the Agent (read-only guardrail)

---

## Stage 7 — Full-System Testing

- [ ] Every failure condition (FC-1 through FC-10 in `TRACEABILITY_MATRIX.md`) has a passing fault-injection test with an *observed* outcome
- [ ] Stress test confirms cycle latency budget holds under rapid-fire cadence
- [ ] Stress test confirms memory/context size stays bounded over a multi-day simulated run
- [ ] Recovery test confirms restart-without-duplication across at least three different kill points (mid-warmup, mid-run, immediately post-commit)
- [ ] Regression test (golden run, deterministic sampling) passes within tolerance band
- [ ] Acceptance criteria A1 through A5 all independently demonstrated in one consolidated test report

---

## Stage 8 — Deployment & Demo

- [ ] Dockerfile per component (Bridge, LLM server, MCP server) with minimal filesystem/network privileges (ADR-011)
- [ ] Full-annual baseline run produced and archived (Parquet export, `11_Database_Design.md` §5)
- [ ] Representative-day agent run produced and archived
- [ ] Demo video captures: live data transfer, AI reasoning, control action generation, dynamic parameter update, end-to-end operation
- [ ] Presentation assembled per the brief's required sections (problem, approach, architecture, setup, results, evaluation, future work)
- [ ] Fallback plan for demo-day hardware unavailability documented and rehearsed (R-09)

---

## Cross-cutting (apply throughout, not tied to one stage)

- [ ] No module outside `bridge/` imports `pyenergyplus`
- [ ] No module outside `bridge/` and `mcp_server/tools/apply_setpoints.py` calls an actuator-writing function
- [ ] No tool in `mcp_server/tools/` grants shell, file-write, or code-execution capability
- [ ] Every write path (`apply_setpoints`, `log_decision`, `raise_incident`) is idempotent by `cycle_id`
- [ ] Every config field has a documented default and a validation rule
- [ ] Every module listed in `MODULE_BREAKDOWN.md` has both the required unit tests and (where applicable) integration tests present in the repository
