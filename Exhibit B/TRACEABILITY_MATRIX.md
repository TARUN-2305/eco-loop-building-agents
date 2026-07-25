# TRACEABILITY_MATRIX.md

Every requirement in `01_Requirements.md` is mapped below — functional, non-functional, performance, reliability, safety, energy, comfort, latency, scalability, failure conditions, edge cases, and acceptance criteria. Nothing in `01_Requirements.md` is left unmapped; where a requirement is a documentation/scope assertion rather than a runtime behavior, that is stated explicitly rather than forcing a fabricated test. Module paths follow `MODULE_BREAKDOWN.md` / `REPOSITORY_STRUCTURE.md`.

## Functional Requirements

| ID | Requirement (short) | Architecture Component(s) | Source Doc(s) | Module(s) | Test(s) | Acceptance Criteria | Runtime Verification |
|---|---|---|---|---|---|---|---|
| FR-1 | Run EnergyPlus under external control | Bridge | `02_Architecture.md` §3.1, `07_EnergyPlus_Design.md` | `bridge/lifecycle.py` | `tests/integration/test_bridge_lifecycle.py` | A1 | `runs.status` reaches `completed` |
| FR-2 | Read sensors at decision cadence | Bridge | `05_Runtime_Execution.md` §3 | `bridge/callbacks.py`, `bridge/handles.py` | `tests/integration/test_sensor_read.py` | A1 | `sensor_snapshots` row count matches expected cadence |
| FR-3 | Compute PMV/PPD deterministically | Comfort module | `10_Machine_Learning.md` §6, `09_MCP_Architecture.md` §2.4 | `comfort/pmv.py` | `tests/unit/test_pmv_golden_values.py` | A2 | Golden-value spot check against ISO 7730 reference points |
| FR-4 | Agent reads/writes only via MCP tools | Agent Orchestrator, MCP Server | `02_Architecture.md` §3.2, `09_MCP_Architecture.md` | `agent/orchestrator.py`, `mcp_server/server.py` | `tests/integration/test_no_out_of_band_access.py` (import-boundary check) | A3 | CI-enforced: `agent/` never imports `bridge`/`pyenergyplus` |
| FR-5 | Agent produces typed candidate action | Agent Orchestrator, Optimizer | `06_Control_System.md` §2–3 | `agent/orchestrator.py`, `optimizer/solver.py` | `tests/unit/test_propose_setpoints.py` | A2, A3 | `decision_logs.action_or_incident` always well-typed JSON |
| FR-6 | Every action passes `validate_action` | Validator | `06_Control_System.md` §4, `09_MCP_Architecture.md` §2.6 | `validator/bounds.py` | `tests/unit/test_validate_action_property.py` (property-based fuzz) | A2, A5 | Zero actuator writes bypassing validation, cross-checked via `decision_logs.trace_json` |
| FR-7 | Validated actions applied + logged with `cycle_id` | Bridge, MCP Server | `05_Runtime_Execution.md` §4, `09_MCP_Architecture.md` §2.7/§2.9 | `bridge/handles.py`, `mcp_server/tools/apply_setpoints.py`, `mcp_server/tools/log_decision.py` | `tests/integration/test_commit_and_log.py` | A2 | Every `committed` `decision_logs` row has a matching actuator value on next `get_zone_state` |
| FR-8 | Fallback to last known-good on failure | Bridge | `05_Runtime_Execution.md` §4 step 5, SR-4 | `bridge/handles.py` | `tests/fault_injection/test_fallback_paths.py` | A1, A3, A5 | `decision_logs.outcome=fallback` ratio measured directly (feeds A3's <5% target) |
| FR-9 | Baseline vs. agent, same model, comparable | Config, Storage | `00_Project_Overview.md` §3.1, `11_Database_Design.md` §6 | `config/schema.py` (`run_mode`), `storage/schema.py` (`runs.run_mode`) | `tests/simulation/test_baseline_vs_agent_run.py` | A2 | `compare_runs` succeeds for a given (baseline, agent) `run_id` pair |
| FR-10 | Aggregated end-of-run report | Analytics, Dashboard | `03_Component_Design.md` §7–8, `12_API_Design.md` §2 | `analytics/aggregate.py`, `dashboard/app.py` | `tests/integration/test_run_summary.py` | A2 | `run_summaries` row exists; dashboard renders within PR-4 budget |
| FR-11 | ECM sweep via offline `eppy`, distinct from runtime loop | idf_tools (explicitly not Bridge) | `07_EnergyPlus_Design.md` §4 | `idf_tools/ecm_sweep.py` | `tests/unit/test_ecm_sweep_generation.py` | A4 | Generated `.idf` variants pass EnergyPlus's own IDD validation |
| FR-12 | Log every tool call, args, result, cycle | MCP Server, Agent | `09_MCP_Architecture.md` §2.9, `04_Dataflow.md` §1 | `mcp_server/server.py` (call-logging middleware) | `tests/integration/test_tool_call_logging.py` | A5 | `decision_logs.trace_json` call count matches MCP server's own count per `cycle_id` |
| FR-13 | Inspect why an action was taken | Analytics | `03_Component_Design.md` §5, `12_API_Design.md` §2 | `analytics/aggregate.py` (`get_decision_trace`) | `tests/integration/test_decision_trace_retrieval.py` | A5 | Given a `cycle_id`, returns non-empty `rationale` + full `trace_json` |

## Non-Functional Requirements

| ID | Requirement (short) | Component(s) | Source Doc(s) | Module(s) | Test(s) | Acceptance Criteria | Runtime Verification |
|---|---|---|---|---|---|---|---|
| NFR-1 | Independently testable components | All | `03_Component_Design.md` (every section) | every module's own test directory | `tests/unit/*` (each with dependencies mocked) | A4 | CI runs each component's unit tests with the others mocked |
| NFR-2 | Linux/macOS portability | Environment/CI | `00_Project_Overview.md` assumption 4 | `.github/workflows/ci.yml` (OS matrix) | CI itself | A4 | CI green on both OS runners |
| NFR-3 | Externalized configuration | Configuration | `03_Component_Design.md` §10, `12_API_Design.md` §3 | `config/schema.py`, `config/loader.py` | `tests/unit/test_config_validation.py` | A4 | Schema-completeness test: every field named in NFR-3 has a config field |
| NFR-4 | Structured logs, `cycle_id`-threaded | Shared logging | `03_Component_Design.md` §6 | `shared/logging.py` | `tests/unit/test_log_correlation_id.py` | A4 | Log lines from a single cycle share one `cycle_id` |
| NFR-5 | Reproducibility under deterministic sampling | Agent (LLM client) | `13_Testing.md` §9, `08_LLM_and_Agent_System.md` | `agent/llm_client.py` (temperature/seed config) | `tests/regression/test_golden_run.py` | A4 | Golden-run metrics within tolerance band across repeated deterministic runs |

## Performance Requirements

| ID | Requirement (short) | Component(s) | Source Doc(s) | Module(s) | Test(s) | Acceptance Criteria | Runtime Verification |
|---|---|---|---|---|---|---|---|
| PR-1 | ≤8s P95 decision-cycle latency | Agent, Bridge (cycle timeout) | `15_Performance.md` §1–2 | `agent/orchestrator.py` | `tests/stress/test_cycle_latency_budget.py` | A1 | P95 computed from `decision_logs` timestamps |
| PR-2 | Full-annual baseline <1hr | Bridge (baseline mode) | `01_Requirements.md` PR-2 | `bridge/lifecycle.py` | `tests/simulation/test_full_annual_baseline_runtime.py` | A2 | Wall-clock time measured directly |
| PR-3 | Representative-day sampling, not full-annual AI run | Config, Bridge | ADR-009, `01_Requirements.md` PR-3 | `config/schema.py` (`representative_days`), `bridge/lifecycle.py` | `tests/simulation/test_representative_day_selection.py` | A2 | Agent-mode run only executes over configured windows |
| PR-4 | Dashboard render ≤5s | Dashboard, Analytics | `15_Performance.md`, `11_Database_Design.md` §3 | `dashboard/app.py` | `tests/integration/test_dashboard_render_time.py` | A2 | Measured render time |

## Reliability Requirements

| ID | Requirement (short) | Component(s) | Source Doc(s) | Module(s) | Test(s) | Acceptance Criteria | Runtime Verification |
|---|---|---|---|---|---|---|---|
| RR-1 | LLM failure doesn't crash simulation | Agent, Bridge | `05_Runtime_Execution.md` §4 step 5 | `agent/orchestrator.py`, `bridge/handles.py` | `tests/fault_injection/test_llm_unreachable.py` | A1, A5 | Run reaches `Completed` despite injected LLM failure |
| RR-2 | Retry read-only, never blind-retry `apply_setpoints` | Agent (tool-calling logic) | `04_Dataflow.md` §4 | `agent/orchestrator.py` (tool-call wrapper) | `tests/unit/test_retry_policy.py` | A5 | Unit test: transient failure retried for `get_weather_forecast`, not for `apply_setpoints` |
| RR-3 | Degraded mode after N unreachable cycles | Agent, Monitoring | `03_Component_Design.md` §11 | `agent/orchestrator.py`, `monitoring/health.py` | `tests/fault_injection/test_degraded_mode.py` | A1, A5 | After 3 consecutive unreachable cycles, monitoring reports `degraded`; run continues |
| RR-4 | Fatal EnergyPlus error → graceful termination | Bridge | `05_Runtime_Execution.md` §6 | `bridge/lifecycle.py` | `tests/fault_injection/test_fatal_error_handling.py` | A5 | `run_summaries.status=incomplete`; buffered telemetry present up to failure point |
| RR-5 | Restartable without duplication | Storage | `05_Runtime_Execution.md` §6, `11_Database_Design.md` §6 | `storage/schema.py`, `storage/writer.py` | `tests/recovery/test_restart_no_duplication.py` | A5 | Row counts consistent after simulated kill-and-restart |

## Safety Requirements

| ID | Requirement (short) | Component(s) | Source Doc(s) | Module(s) | Test(s) | Acceptance Criteria | Runtime Verification |
|---|---|---|---|---|---|---|---|
| SR-1 | Hard-coded, physics-informed actuator bounds | Validator, Config | `14_Security.md` §4, `09_MCP_Architecture.md` §2.6 | `validator/bounds.py`, `configs/*.yaml` | `tests/unit/test_validator_bounds_property.py` | A5 | Property-based fuzz test: 100% correct pass/fail vs. configured bounds |
| SR-2 | Unlisted actuators rejected, not attempted | Validator, `apply_setpoints` | `09_MCP_Architecture.md` §2.7 | `validator/bounds.py`, `mcp_server/tools/apply_setpoints.py` | `tests/unit/test_unlisted_actuator_rejected.py` | A5 | Explicit unlisted-actuator test case rejected at both layers |
| SR-3 | No shell/file-write/code-exec tool | MCP Server tool catalog | `14_Security.md` §5, ADR-011 | `mcp_server/server.py` (fixed registration list) | `tests/integration/test_tool_catalog_is_fixed.py` | A5 | CI asserts exactly the ten named tools are registered, nothing else |
| SR-4 | Prefer safest known state on failure | Bridge | `05_Runtime_Execution.md` §4 step 5 | `bridge/handles.py` | Same as FR-8/RR-1 | A5 | Same as FR-8 |
| SR-5 | Safety case rests on simulation-only; not certified for real hardware | Scope/documentation (not code) | `00_Project_Overview.md` §3.2, `14_Security.md` §4 | N/A — this is a documentation/scope assertion, not an executable behavior | N/A | A4 | Verified by documentation review (this Project Bible states the boundary explicitly), not by a runtime test |

## Energy Constraints

| ID | Requirement (short) | Component(s) | Source Doc(s) | Module(s) | Test(s) | Acceptance Criteria | Runtime Verification |
|---|---|---|---|---|---|---|---|
| EC-1 | Energy as objective term, from meter output | Optimizer | `06_Control_System.md` §3 | `optimizer/solver.py` | `tests/unit/test_optimizer_objective.py` | A2 | `propose_setpoints` output always includes `predicted_kwh_horizon` |
| EC-2 | Peak demand as hard constraint, not soft cost | Optimizer, Validator | `06_Control_System.md` §3 | `optimizer/solver.py`, `validator/bounds.py` | `tests/unit/test_peak_demand_constraint.py` | A2 | No proposed or validated action exceeds a configured threshold |
| EC-3 | Carbon signal optional, never overrides EC-1/EC-2 | Optimizer, `get_utility_signal` | `09_MCP_Architecture.md` §2.3, `06_Control_System.md` §3 | `optimizer/solver.py`, `mcp_server/tools/get_utility_signal.py` | `tests/unit/test_carbon_aware_toggle.py` | A2 | `carbon_aware: false` → signal null and ignored; `true` → EC-1/EC-2 still binding |

## Comfort Constraints

| ID | Requirement (short) | Component(s) | Source Doc(s) | Module(s) | Test(s) | Acceptance Criteria | Runtime Verification |
|---|---|---|---|---|---|---|---|
| CC-1 | Target ±0.5 PMV during occupied hours | Validator, Comfort module | `01_Requirements.md` §7 | `validator/bounds.py`, `comfort/pmv.py` | `tests/unit/test_comfort_bands.py` | A2 | Analytics computes % compliance against ±0.5 |
| CC-2 | Hard ±1.5 PMV band, validator rejects violations | Validator | `06_Control_System.md` §3 | `validator/bounds.py` | `tests/unit/test_comfort_bands.py` | A2, A5 | Property test: no validated action predicted to exceed ±1.5 |
| CC-3 | Unoccupied-hour exemption | Config, Analytics | `01_Requirements.md` §7 | `config/schema.py`, `analytics/aggregate.py` | `tests/unit/test_occupancy_exemption.py` | A2 | Compliance % excludes unoccupied timesteps by default |

## Latency Requirements

| ID | Requirement (short) | Component(s) | Source Doc(s) | Module(s) | Test(s) | Acceptance Criteria | Runtime Verification |
|---|---|---|---|---|---|---|---|
| LR-1 | ≤8s P95 end-to-end cycle latency | Agent, LLM client | `15_Performance.md` §1 | `agent/orchestrator.py` | `tests/stress/test_latency_budgets.py` | A1 | Same measurement as PR-1 |
| LR-2 | Measurable prefix-caching benefit | Agent, LLM client | `15_Performance.md` §2 | `agent/llm_client.py` | `tests/stress/test_prefix_cache_benefit.py` (one-time setup verification) | A1 | Time-to-first-token compared cold vs. cached, once per environment setup |
| LR-3 | ≤200ms P95 deterministic tool round-trip | MCP Server | `01_Requirements.md` LR-3 | `mcp_server/tools/*.py` | `tests/stress/test_latency_budgets.py` | A1 | Per-tool latency histogram from MCP server logs |

## Scalability

| ID | Requirement (short) | Component(s) | Source Doc(s) | Module(s) | Test(s) | Acceptance Criteria | Runtime Verification |
|---|---|---|---|---|---|---|---|
| SC-1 | No hard-coded single-building assumption | Config, Storage | `01_Requirements.md` §9 | `config/schema.py` (`building_id`), `storage/schema.py` | `tests/unit/test_building_id_threading.py` | A4 | Every table/tool schema includes `building_id`, even with one configured value |
| SC-2 | Multi-building achievable via process replication | Architecture (design constraint, not built) | `02_Architecture.md` §9 | N/A — a constraint on how `bridge/`+`agent/` are structured, not a module to build in this phase | N/A | A4 | Verified by architecture review: no module holds process-global state that would prevent a second instance |

## Failure Conditions (§10 of `01_Requirements.md`)

| ID | Condition | Component(s) | Test | Acceptance Criteria |
|---|---|---|---|---|
| FC-1 | LLM server unreachable | Agent, Bridge | `tests/fault_injection/test_llm_unreachable.py` | A5 |
| FC-2 | Malformed/unparseable tool call | Agent, MCP Server | `tests/fault_injection/test_malformed_tool_call.py` | A5 |
| FC-3 | Semantically out-of-bound but well-formed action | Validator | `tests/fault_injection/test_out_of_bound_action.py` | A5 |
| FC-4 | LLM call exceeds latency budget | Agent (cycle timeout) | `tests/fault_injection/test_llm_timeout.py` | A5 |
| FC-5 | EnergyPlus recoverable severe warning | Bridge | `tests/fault_injection/test_recoverable_warning.py` | A5 |
| FC-6 | EnergyPlus fatal error | Bridge | `tests/fault_injection/test_fatal_error_handling.py` | A5 |
| FC-7 | Database write failure | Storage | `tests/fault_injection/test_storage_write_failure.py` | A5 |
| FC-8 | Concurrent `apply_setpoints` for same `cycle_id` | MCP Server (`apply_setpoints`) | `tests/fault_injection/test_concurrent_apply.py` | A5 |
| FC-9 | Process killed and restarted mid-run | Storage, Bridge | `tests/recovery/test_restart_no_duplication.py` | A5 |
| FC-10 | Config-actuator/`.idf` mismatch | Config | `tests/unit/test_config_validation.py` | A4/A5 |

## Edge Cases (§12 of `01_Requirements.md`)

| ID | Case | Component(s) | Test | Acceptance Criteria |
|---|---|---|---|---|
| EDGE-1 | Warmup period | Bridge | `tests/integration/test_edge_cases.py::test_warmup_gating` | A1 |
| EDGE-2 | Design-day vs. run-period environments | Bridge | `tests/integration/test_edge_cases.py::test_environment_detection` | A1 |
| EDGE-3 | Extreme/out-of-design weather | Validator, Optimizer | `tests/simulation/test_extreme_weather_infeasible.py` | A2, A5 |
| EDGE-4 | DST/schedule-boundary transitions | Bridge | `tests/integration/test_edge_cases.py::test_time_boundary` | A1 |
| EDGE-5 | Cold start, no history | `get_history` tool | `tests/unit/test_no_comparable_history.py` | A5 |
| EDGE-6 | Extended occupancy=0 (holiday) | Config, Analytics | `tests/unit/test_occupancy_exemption.py` | A2 |

## Acceptance Criteria (§11 of `01_Requirements.md`) — roll-up view

| ID | Criterion | Fed by requirements | Runtime Verification |
|---|---|---|---|
| A1 | ≥99% clean cycles, 0 attributable fatal aborts | FR-1, FR-2, FR-8, PR-1, RR-1, RR-3, EDGE-1, EDGE-2, EDGE-4 | Computed in Analytics from `decision_logs`/`run_summaries` at run end |
| A2 | Positive energy reduction AND comfort compliance ≥ baseline | FR-3, FR-9, FR-10, PR-2, PR-3, PR-4, EC-1–3, CC-1–3, EDGE-3, EDGE-6 | `compare_runs` output, specifically the `comfort_not_sacrificed` boolean |
| A3 | <5% fallback-controller invocation | FR-8, FR-6, FR-5, FR-4 | `decision_logs.outcome=fallback` ratio |
| A4 | All 18 Project Bible documents + this implementation package present and cross-referenced | NFR-1–5, SC-1–2, SR-5, FC-10 | Documentation completeness review (this matrix itself is part of that evidence) |
| A5 | Every failure condition has an observed graceful-degradation test | RR-1–5, SR-1–4, FC-1–9 | `tests/fault_injection/*`, `tests/recovery/*` all passing |

## Final review for this document

- [x] Every ID from `01_Requirements.md` (FR-1–13, NFR-1–5, PR-1–4, RR-1–5, SR-1–5, EC-1–3, CC-1–3, LR-1–3, SC-1–2, FC-1–10, EDGE-1–6, A1–5) appears exactly once above.
- [x] No row invents a component, module, or test not already named somewhere in the Project Bible or in `MODULE_BREAKDOWN.md`/`REPOSITORY_STRUCTURE.md`.
- [x] Rows that cannot be mapped to an executable test (SR-5, SC-2) say so explicitly rather than being forced into a fabricated one.
