# MODULE_BREAKDOWN.md

Thirteen modules, one per component in `03_Component_Design.md` plus a `shared/` module for cross-cutting types and logging that `03_Component_Design.md` referenced implicitly (structured logging, `NFR-4`) but didn't name as its own component — recorded here as an **implementation assumption**, not a new architectural component: it holds no behavior of its own, only shared type definitions and the logging wrapper every other module imports.

---

## `shared/`

- **Purpose**: cross-cutting types and the structured-logging wrapper, so no two modules define their own competing version of `SensorSnapshot` or reinvent `cycle_id`-threaded logging.
- **Responsibilities**: typed data records for every message type in `04_Dataflow.md` §1 (`SensorSnapshot`, `CandidateAction`, `ValidationResult`, `DecisionLog`, `Incident`, `RunSummary`); a JSON structured-logging wrapper enforcing `cycle_id` inclusion where applicable.
- **Public interfaces**: the record/dataclass (or pydantic model) definitions themselves; `get_logger(component_name) -> Logger`.
- **Inputs**: none (pure type/utility module).
- **Outputs**: typed objects consumed by every other module.
- **Dependencies**: none within this project (this is intentionally the one module everything else may depend on, and which depends on nothing else here).
- **Files expected**: `shared/types.py`, `shared/logging.py`, `shared/__init__.py`.
- **Estimated size**: ~150–250 lines total.
- **Unit tests required**: schema/type validation for each record type; log-formatting correctness (valid JSON, `cycle_id` present when supplied).
- **Integration tests required**: none — this module has no external interaction to integration-test.

---

## `config/`

- **Purpose**: single source of truth for run configuration (`03_Component_Design.md` §10, `12_API_Design.md` §3).
- **Responsibilities**: schema definition; load-and-validate; fail-fast on missing/inconsistent fields (e.g., `agent` mode with no LLM endpoint; an actuator not resolvable against the loaded `.idf`, per `01_Requirements.md` §12's named edge case).
- **Public interfaces**: `load_config(path) -> Config`; `Config` is otherwise read-only.
- **Inputs**: a YAML/JSON config file; (for actuator validation specifically) a loaded `.idf`'s resolvable-actuator list, obtained via a one-time call into `bridge/` at startup.
- **Outputs**: a validated, typed `Config` object every other module reads at startup.
- **Dependencies**: `shared/` (for shared types where config fields reference them); a narrow, startup-only dependency on `bridge/` for actuator-name cross-validation (this is the one place `config/` reaches into another module, and only at process start, never during a run).
- **Files expected**: `config/schema.py`, `config/loader.py`, `config/__init__.py`.
- **Estimated size**: ~300–400 lines.
- **Unit tests required**: valid config loads; each documented failure mode (missing LLM endpoint, unresolvable actuator, malformed comfort band) rejected with a specific error.
- **Integration tests required**: end-to-end load against a real `.idf` file's actuator list.

---

## `bridge/`

- **Purpose**: the sole interface to `pyenergyplus` (`03_Component_Design.md` §1, `02_Architecture.md` §3.1's "Bridge is the only EnergyPlus interface" guardrail).
- **Responsibilities**: state creation and lifecycle; callback registration at the specific calling points named in `07_EnergyPlus_Design.md` §2; handle resolution and caching, gated on `api_data_fully_ready`; warmup/environment-phase detection; actuator commit with `cycle_id` idempotency; fallback (last-known-good) re-assertion.
- **Public interfaces**: `run(config) -> RunResult`; the internal `on_decision_cycle` hook it calls out to (implemented by `agent/`, injected as a callback at startup — Bridge does not import `agent/` directly, it receives a callable).
- **Inputs**: `Config`, `.idf` path, `.epw` path.
- **Outputs**: `SensorSnapshot` stream (to `storage/`, async); `RunResult`/`RunSummary` status at completion.
- **Dependencies**: `shared/`, `pyenergyplus` (external), `comfort/` (calls `compute_pmv` every timestep, per `05_Runtime_Execution.md` §3).
- **Files expected**: `bridge/lifecycle.py`, `bridge/callbacks.py`, `bridge/handles.py`, `bridge/__init__.py`.
- **Estimated size**: ~600–900 lines — the largest single module, reflecting `07_EnergyPlus_Design.md`'s documented complexity (callback timing, handle caching, warmup gating).
- **Unit tests required**: handle-caching logic with a mocked `pyenergyplus.api`; warmup/environment-phase detection logic in isolation.
- **Integration tests required**: a real short design-day run against a real EnergyPlus process (`tests/integration/test_bridge_lifecycle.py`); actuator commit round-trip.

---

## `comfort/`

- **Purpose**: the deterministic PMV/PPD calculation (`10_Machine_Learning.md` §6, ADR-010).
- **Responsibilities**: implement Fanger's model exactly; validate inputs against ASHRAE 55's documented applicability bounds; expose the same function both to the Bridge (called every timestep) and to the MCP `compute_pmv` tool (called on demand), so there is exactly one PMV implementation in the codebase, not two that could drift apart.
- **Public interfaces**: `compute_pmv(air_temp_c, mean_radiant_temp_c, air_speed_ms, rh_pct, met_rate, clo) -> PMVResult`.
- **Inputs**: the six named physical quantities.
- **Outputs**: `PMVResult { pmv, ppd_pct }`.
- **Dependencies**: `shared/` only.
- **Files expected**: `comfort/pmv.py`, `comfort/__init__.py`.
- **Estimated size**: ~100–150 lines (a small, pure, formula-driven module — size should not grow; growth here would be a signal something's wrong, given the underlying model is a fixed equation).
- **Unit tests required**: golden-value tests against published ISO 7730 reference input/output pairs; boundary-input rejection tests.
- **Integration tests required**: none required beyond the MCP contract test (`09_MCP_Architecture.md` §2.4), which lives in `mcp_server/`'s integration suite.

---

## `optimizer/`

- **Purpose**: the deterministic setpoint solver behind `propose_setpoints` (`06_Control_System.md` §2–3, ADR-005).
- **Responsibilities**: bounded-horizon search over the allow-listed actuator ranges given objective weights; enforce hard constraints (comfort hard band, peak-demand threshold) as constraints, not penalties; return `infeasible` honestly when no candidate satisfies them.
- **Public interfaces**: `propose(objective_weights, horizon_steps, current_state, forecast, carbon_aware) -> Candidate | Infeasible`.
- **Inputs**: objective weights, horizon length, current `SensorSnapshot`, forecast window, allow-list bounds (from `Config`).
- **Outputs**: a candidate action plus predicted kWh/PMV range, or an explicit infeasibility result.
- **Dependencies**: `shared/`, `config/` (bounds), `comfort/` (to evaluate predicted PMV of a candidate).
- **Files expected**: `optimizer/solver.py`, `optimizer/__init__.py`.
- **Estimated size**: ~300–500 lines.
- **Unit tests required**: never returns out-of-bound candidates (defense-in-depth alongside the Validator); correctly reports `infeasible` rather than silently clamping; objective-weight sensitivity (higher `w_comfort_penalty` measurably changes the candidate).
- **Integration tests required**: MCP contract test for `propose_setpoints` (lives in `mcp_server/`'s suite).

---

## `validator/`

- **Purpose**: the single, non-negotiable safety gate (`06_Control_System.md` §4, SR-1–SR-4, ADR-005).
- **Responsibilities**: pure, total, deterministic bound-checking against the config-loaded allow-list; return specific, actionable failure reasons.
- **Public interfaces**: `validate(candidate, allow_list) -> ValidationResult`.
- **Inputs**: a candidate action, the allow-list bound table.
- **Outputs**: `ValidationResult { valid: bool, reasons: [str] }`.
- **Dependencies**: `shared/` only — deliberately zero dependency on `optimizer/`, `agent/`, or any I/O, so it can be property-tested in total isolation.
- **Files expected**: `validator/bounds.py`, `validator/__init__.py`.
- **Estimated size**: ~150–250 lines — kept deliberately small; this is the single highest-scrutiny module in the codebase (`16_Risk_Register.md` R-01) and complexity here is a liability, not a feature.
- **Unit tests required**: exhaustive property-based fuzz testing (`13_Testing.md` §2, §8) — this module's test suite is expected to be larger than the module itself.
- **Integration tests required**: MCP contract test for `validate_action`; the server-side re-validation check inside `apply_setpoints` (lives in `mcp_server/`).

---

## `agent/`

- **Purpose**: the ReAct-style decision loop and its memory (`08_LLM_and_Agent_System.md`, `03_Component_Design.md` §3/§5).
- **Responsibilities**: assemble per-cycle context; run the reasoning/tool-calling loop within the tool-call budget and cycle timeout; enforce the retry-vs-no-retry distinction per tool (`04_Dataflow.md` §4); maintain the two-tier memory (rolling window + periodic reflection); escalate to `raise_incident` on failure.
- **Public interfaces**: the `on_decision_cycle(snapshot, cycle_id) -> Action | None` function the Bridge invokes; `end_of_day_reflect()` invoked on a simulated-day boundary.
- **Inputs**: `SensorSnapshot`, `cycle_id`, `Config` (cadence, budget, timeout, LLM endpoint).
- **Outputs**: a committed `Action` or a fallback signal, plus a full `DecisionLog` trace.
- **Dependencies**: `shared/`, `config/`, an MCP client (talking to `mcp_server/` over stdio — never importing `mcp_server/`'s internals directly), an LLM client (talking to the external inference server).
- **Files expected**: `agent/orchestrator.py`, `agent/memory.py`, `agent/llm_client.py`, `agent/__init__.py`.
- **Estimated size**: ~500–700 lines.
- **Unit tests required**: loop logic with a scripted/mocked LLM (no real inference); retry-policy unit tests; memory rolling-window and reflection-summary behavior in isolation.
- **Integration tests required**: full loop against real MCP tools with a scripted LLM stub (`13_Testing.md` §3); full loop against a real LLM endpoint for at least one representative-day run.

---

## `mcp_server/`

- **Purpose**: the fixed, ten-tool agent-facing capability surface (`09_MCP_Architecture.md`).
- **Responsibilities**: tool registration (exactly ten, no dynamic registration mechanism — SR-3, ADR-011); request/response schema validation at the boundary; the protocol-vs-execution error distinction; call logging (FR-12) as middleware wrapping every tool invocation.
- **Public interfaces**: the MCP server process itself (stdio transport); each tool's schema as defined verbatim in `09_MCP_Architecture.md` §2.
- **Inputs**: `tools/call` requests from `agent/`.
- **Outputs**: tool results (success or `isError`) per `09_MCP_Architecture.md`.
- **Dependencies**: `shared/`, `config/`, `bridge/` (for `get_zone_state`, `apply_setpoints`), `storage/` (for `get_history`, `log_decision`, `raise_incident`), `comfort/`, `optimizer/`, `validator/`.
- **Files expected**: `mcp_server/server.py`, `mcp_server/tools/get_zone_state.py`, `mcp_server/tools/get_weather_forecast.py`, `mcp_server/tools/get_utility_signal.py`, `mcp_server/tools/compute_pmv.py`, `mcp_server/tools/propose_setpoints.py`, `mcp_server/tools/validate_action.py`, `mcp_server/tools/apply_setpoints.py`, `mcp_server/tools/get_history.py`, `mcp_server/tools/log_decision.py`, `mcp_server/tools/raise_incident.py`, `mcp_server/__init__.py`.
- **Estimated size**: ~700–1000 lines across the tool files (each tool file is thin — most logic lives in `comfort/`, `optimizer/`, `validator/`, `bridge/`, `storage/`; the tool files are schema-validating adapters, not where the real logic lives).
- **Unit tests required**: schema validation for every tool's input/output; error-shape correctness for every documented `isError` case.
- **Integration tests required**: full contract test suite (one per tool, `13_Testing.md` §3); the "exactly ten tools registered" CI check (SR-3).

---

## `storage/`

- **Purpose**: durable telemetry and decision record (`03_Component_Design.md` §9, `11_Database_Design.md`).
- **Responsibilities**: schema management; the async write buffer and its documented backpressure priority (`04_Dataflow.md` §3); `run_id`-keyed isolation between runs.
- **Public interfaces**: `write_snapshot(snapshot)`, `write_decision_log(log)`, `write_incident(incident)` (all async/fire-and-forget); `query(...)` (used by `analytics/` and the `get_history` tool).
- **Inputs**: `SensorSnapshot`, `DecisionLog`, `Incident` records.
- **Outputs**: persisted rows; query results.
- **Dependencies**: `shared/`, `config/` (backend choice, path).
- **Files expected**: `storage/schema.py`, `storage/writer.py`, `storage/queries.py`, `storage/__init__.py`.
- **Estimated size**: ~400–600 lines.
- **Unit tests required**: backpressure drop-priority logic under a simulated slow sink; idempotent write behavior for repeated `cycle_id`s.
- **Integration tests required**: real DuckDB/SQLite round-trip; restart-without-duplication (`tests/recovery/`).

---

## `analytics/`

- **Purpose**: turn stored rows into the specific required comparison numbers (`03_Component_Design.md` §7, `12_API_Design.md` §2).
- **Responsibilities**: `run_summary` aggregation; `compare_runs`' identical-methodology baseline-vs-agent computation; `get_decision_trace` retrieval.
- **Public interfaces**: `get_run_summary(run_id)`, `compare_runs(baseline_run_id, agent_run_id)`, `get_timeseries(...)`, `get_incident_log(run_id)`, `get_decision_trace(cycle_id)`.
- **Inputs**: `run_id`(s) or `cycle_id`.
- **Outputs**: `RunSummary`, comparison records, time series for charting.
- **Dependencies**: `shared/`, `storage/` (read-only).
- **Files expected**: `analytics/aggregate.py`, `analytics/__init__.py`.
- **Estimated size**: ~300–450 lines.
- **Unit tests required**: aggregation correctness against a fixture dataset with known expected totals.
- **Integration tests required**: `compare_runs` against a real (baseline, agent) run pair.

---

## `dashboard/`

- **Purpose**: read-only presentation (`03_Component_Design.md` §8).
- **Responsibilities**: render `RunSummary` and time-series charts; nothing else — no write path exists in this module by construction (the "Dashboard is read-only" guardrail).
- **Public interfaces**: a local web app entry point (`dashboard/app.py`) reading exclusively from `analytics/`.
- **Inputs**: `run_id`(s) selected by the person viewing it.
- **Outputs**: rendered HTML/charts.
- **Dependencies**: `shared/`, `analytics/` only.
- **Files expected**: `dashboard/app.py`, `dashboard/templates/` or equivalent, `dashboard/__init__.py`.
- **Estimated size**: ~300–500 lines plus templates.
- **Unit tests required**: rendering logic against fixture `RunSummary` data (no live run required).
- **Integration tests required**: render-time budget test (PR-4) against a full representative-day dataset.

---

## `idf_tools/`

- **Purpose**: offline ECM sweep generation (FR-11, `07_EnergyPlus_Design.md` §4).
- **Responsibilities**: use `eppy` to produce modified `.idf` variants from a baseline; validate each variant against EnergyPlus's own IDD before queuing it as a separate run. **Never** touches a running simulation.
- **Public interfaces**: `generate_ecm_variants(baseline_idf_path, ecm_definitions) -> [idf_path]`.
- **Inputs**: baseline `.idf`, a list of ECM parameter changes (e.g., insulation levels, HVAC system swaps).
- **Outputs**: one or more new `.idf` files on disk.
- **Dependencies**: `shared/`, `eppy` (external) — explicitly **no** dependency on `bridge/`, `mcp_server/`, or `agent/`.
- **Files expected**: `idf_tools/ecm_sweep.py`, `idf_tools/__init__.py`.
- **Estimated size**: ~200–350 lines.
- **Unit tests required**: generated variants pass IDD validation; parameter substitution correctness against known inputs.
- **Integration tests required**: a generated variant successfully runs as an independent EnergyPlus simulation.

---

## `monitoring/`

- **Purpose**: live operator-visible health signal, distinct from the durable log/telemetry record (`03_Component_Design.md` §11).
- **Responsibilities**: track cycle latency, fallback-invocation rate, LLM-reachability status; expose a simple health surface.
- **Public interfaces**: `report_cycle(latency_ms, outcome)`, `get_health() -> HealthStatus`.
- **Inputs**: per-cycle outcome/latency events from `agent/`.
- **Outputs**: a `HealthStatus` (nominal/degraded) queryable at any time.
- **Dependencies**: `shared/` only.
- **Files expected**: `monitoring/health.py`, `monitoring/__init__.py`.
- **Estimated size**: ~150–200 lines.
- **Unit tests required**: degraded-mode threshold logic (3 consecutive unreachable cycles, per RR-3).
- **Integration tests required**: `tests/fault_injection/test_degraded_mode.py` (shared with `agent/`'s suite, since the behavior spans both modules).
