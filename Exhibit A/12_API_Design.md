# 12 — API Design

The agent-facing tool surface (schemas, errors, timeouts, retries) is fully specified in `09_MCP_Architecture.md` and is not repeated here. This document covers the **other** internal interfaces: the Bridge's own internal contract, the Analytics/Dashboard read surface, and the Configuration schema — the APIs that exist even though no LLM ever calls them directly.

## 1. Bridge internal interface

This is the boundary between "EnergyPlus-specific code" and "everything else" (`03_Component_Design.md` §1) — the rest of the system is written against this interface and never imports `pyenergyplus` directly, which is what makes the Agent Orchestrator and MCP tools independently testable with a mocked Bridge.

| Method | Direction | Request | Response | Errors |
|---|---|---|---|---|
| `on_decision_cycle` | Bridge → Agent Orchestrator (synchronous, in-callback) | `{ snapshot: SensorSnapshot, cycle_id: string, forecast_available: bool }` | `{ outcome: "committed" \| "fallback", action: Action \| null }` | Orchestrator-side timeout enforced by the Bridge (bounded wait; on expiry, Bridge treats it as `fallback` itself rather than waiting indefinitely) |
| `get_current_snapshot` | Any component → Bridge | `{}` | `SensorSnapshot` | none (always has a value once past warmup) |
| `commit_actuator` | MCP `apply_setpoints` tool → Bridge | `{ actuator_key: string, value: number, cycle_id: string }` | `{ committed: bool }` | `unknown_actuator`, `cycle_id_action_mismatch` (mirrors §2.7 of `09_MCP_Architecture.md`; this is the same idempotency contract, just at the layer below the MCP tool wrapper) |
| `hold_last_known_good` | Agent Orchestrator (on fallback) → Bridge | `{ cycle_id: string, reason: string }` | `{ held: bool, value_in_effect: number }` | none |

## 2. Analytics API (consumed by the Dashboard, and available for ad hoc inspection)

| Endpoint (conceptual — local function call or thin local HTTP wrapper, not a public network API) | Request | Response |
|---|---|---|
| `get_run_summary(run_id)` | `{ run_id: string }` | `RunSummary` (`11_Database_Design.md` §6) |
| `compare_runs(baseline_run_id, agent_run_id)` | `{ baseline_run_id: string, agent_run_id: string }` | `{ pct_energy_reduction: number, baseline_pmv_compliance_pct: number, agent_pmv_compliance_pct: number, comfort_not_sacrificed: bool }` — `comfort_not_sacrificed` is computed as `agent_pmv_compliance_pct >= baseline_pmv_compliance_pct`, directly implementing acceptance criterion S5/A2 from `00_Project_Overview.md`/`01_Requirements.md` as a single boolean the dashboard can render as a clear pass/fail, not just a number the reviewer has to interpret themselves |
| `get_timeseries(run_id, zone_id, fields, resolution)` | `{ run_id, zone_id, fields: [string], resolution: "timestep" \| "hourly" \| "daily" }` | `[{ t: timestamp, ...requested fields }]` for charting |
| `get_incident_log(run_id)` | `{ run_id: string }` | `[Incident]` |
| `get_decision_trace(cycle_id)` | `{ cycle_id: string }` | full `DecisionLog` including `trace_json` — this is the concrete implementation of FR-13 ("inspect why a given action was taken") |

These are described as an internal API surface, not a public one — for the PoC this can be implemented as plain local function calls the Dashboard invokes directly against Storage/Analytics, with a thin HTTP wrapper only if the Dashboard ends up running as a separate process from the analytics code. Nothing here requires authentication or multi-tenant access control per the assumptions in `00_Project_Overview.md`.

## 3. Configuration schema

Loaded once at process start (`03_Component_Design.md` §10); shape, not implementation:

| Section | Fields |
|---|---|
| `simulation` | `idf_path`, `epw_path`, `run_mode` (`baseline` \| `agent`), `representative_days` (list of date ranges, or `full_annual`) |
| `decision_cadence` | `interval_minutes` (default 15) |
| `comfort` | `target_pmv_band` (default `[-0.5, 0.5]`), `hard_pmv_band` (default `[-1.5, 1.5]`) |
| `energy` | `peak_demand_threshold_kw` (nullable), `carbon_aware` (bool, default false) |
| `actuators` | list of `{ logical_name, component_type, control_type, key, min, max }` — the allow-list SR-1/SR-2 depend on; validated against the loaded `.idf`'s actually-resolvable handles at startup, not just accepted blindly |
| `llm` | `endpoint`, `model_name`, `max_tool_calls_per_cycle` (default 6), `cycle_timeout_seconds` (default 8) |
| `storage` | `backend` (`duckdb` \| `sqlite`), `path` |

A config that references an actuator not present in the loaded `.idf`, or a `run_mode: agent` config with no reachable `llm.endpoint`, fails validation at startup — this is the concrete implementation of the edge case named in `01_Requirements.md` §12 and is treated as a hard requirement precisely because a failure here is much cheaper to catch before `run_energyplus` is called than mid-run.

## 4. What is intentionally not exposed as an API

Consistent with `09_MCP_Architecture.md` §4: there is no API to modify the actuator allow-list, comfort bounds, or objective weights from within a running simulation — those are Configuration-time decisions, loaded once, and changing them requires a new run, not a live call. This is a deliberate constraint, not an oversight: it keeps "what could this system possibly do differently between two runs" fully auditable from a single config diff.
