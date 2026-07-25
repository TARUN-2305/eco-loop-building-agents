# 09 — MCP Architecture

## 1. Protocol-level decisions

- **Transport: stdio for the PoC.** The MCP specification currently defines exactly two official transports — stdio for local, same-machine deployments, and Streamable HTTP for remote ones (the older HTTP+SSE transport was deprecated in mid-2025 in favor of Streamable HTTP). Since every component in this PoC runs on one host (`00_Project_Overview.md`, assumption 4), stdio gives the lowest latency and the smallest thing to secure — no network listener, no auth surface, no TLS to configure. **Streamable HTTP is the documented upgrade path** if the MCP server is ever split onto its own host (e.g., a shared tool server for multiple building processes, per `01_Requirements.md` SC-2) — the tool contracts below do not change; only the transport does.
- **Spec version pinning.** This design targets the current published revision (2025-11-25) and is written to be forward-compatible with the imminent 2026-07-28 revision, whose headline changes (a stateless rework of Streamable HTTP, mandatory routing headers, cache-control-style metadata on list/resource results) are transport- and caching-layer changes that do not alter the tools contract this project depends on. The implementation should pin an explicit protocol version at `initialize` time and treat a version mismatch as a startup failure, not a runtime surprise.
- **Primitives used: Tools only, on the server side.** MCP also defines Resources and Prompts as server primitives, and Sampling/Roots/Elicitation as client primitives. This project uses **Tools exclusively** — every piece of building state is fetched through an explicit, model-invoked tool call (not a passively-attached Resource), because every read in this system is something the agent should be *reasoning about deciding to fetch* (a forecast, a history query), not ambient context stuffed in automatically. Elicitation (the client asking a human for input mid-call) is not used, by design: this is an autonomous loop with no human reviewing each cycle in real time — its role is instead played by the deterministic `validate_action` gate (§5).
- **Error model: the protocol-vs-execution distinction is load-bearing.** MCP distinguishes **protocol errors** (unknown tool, bad arguments — standard JSON-RPC error responses) from **tool execution errors** (a tool ran but failed for a domain reason — reported inside a normal result with `isError: true`). This project depends on that distinction: a protocol error means the agent's *call itself* was malformed (a bug, or the model hallucinated a tool name) and is handled by the orchestrator's retry/escalation logic (`04_Dataflow.md` §4); a tool execution error (e.g., `validate_action` returning "fail: setpoint out of range") is handed back to the model **as content it can reason about and act on**, which is exactly how this system's in-cycle self-correction (`05_Runtime_Execution.md` §4, step 4) works.
- **Untrusted-by-default posture.** Per the specification's own security guidance, tool annotations and results are to be treated as untrusted unless they come from a trusted, known server. Since this project's MCP server is first-party and local, the practical risk is lower than a marketplace-of-servers scenario — but the *design pattern* (never let a tool's output silently expand what the agent is allowed to do next) is followed regardless, and is the basis for `14_Security.md` §2.

## 2. Tool catalog

Ten tools, deliberately kept to a small, sharply-described set — current guidance on local/self-hosted tool-calling models is consistent that a smaller active tool catalog with unambiguous descriptions materially improves the reliability of *tool selection*, independent of how good the model is at formatting an individual call (`08_LLM_and_Agent_System.md`, §5).

| Tool | Type | Idempotent? | Typical latency |
|---|---|---|---|
| `get_zone_state` | Read | Yes | < 50 ms |
| `get_weather_forecast` | Read | Yes | < 100 ms |
| `get_utility_signal` | Read | Yes | < 100 ms |
| `compute_pmv` | Pure compute | Yes | < 20 ms |
| `propose_setpoints` | Pure compute (deterministic optimizer) | Yes | < 500 ms |
| `validate_action` | Pure compute | Yes | < 20 ms |
| `apply_setpoints` | Write (side effect on simulation) | Yes, keyed by `cycle_id` | < 100 ms |
| `get_history` | Read (queries the store) | Yes | < 200 ms (bounded window) |
| `log_decision` | Write (append-only) | Yes, keyed by `cycle_id` | Async, non-blocking |
| `raise_incident` | Write (append-only) | Yes, keyed by `cycle_id` | Async, non-blocking |

### 2.1 `get_zone_state`

- **Input schema**: `{ "zone_ids": ["string"] | null }` — `null` or omitted means "all configured zones."
- **Output schema**: `{ "sim_time": "ISO-8601-like sim timestamp", "zones": [ { "zone_id": "string", "air_temp_c": number, "rh_pct": number, "co2_ppm": number | null, "pmv": number, "ppd_pct": number, "current_setpoints": { "heating_c": number, "cooling_c": number } } ] }`
- **Errors**: `isError: true` with `{ "reason": "unknown_zone_id", "zone_id": "..." }` if a requested zone isn't configured.
- **Timeout**: 200 ms (in-memory read from the latest `SensorSnapshot`; a miss almost certainly means a bug, not slowness).
- **Retries**: up to 2, backoff 100 ms — safe, read-only.
- **Example**: request `{ "zone_ids": ["Zone1"] }` → result `{ "sim_time": "Day 145 14:15", "zones": [ { "zone_id": "Zone1", "air_temp_c": 23.4, "rh_pct": 41.2, "co2_ppm": null, "pmv": 0.31, "ppd_pct": 7.1, "current_setpoints": { "heating_c": 21.0, "cooling_c": 24.0 } } ] }`.

### 2.2 `get_weather_forecast`

- **Input**: `{ "horizon_hours": integer (1–48) }`.
- **Output**: `{ "series": [ { "hour_offset": integer, "outdoor_temp_c": number, "outdoor_rh_pct": number, "solar_wm2": number } ] }`.
- **Source (PoC)**: derived deterministically from the same EPW file driving the simulation, read ahead of the current simulated time — a legitimate stand-in for a forecast in a simulation context, explicitly labeled as such in the tool's description so the agent (and any human reading logs) is not misled into thinking this is a live forecast API.
- **Errors**: `isError: true`, `{ "reason": "horizon_exceeds_available_data" }` near the end of the run period.
- **Timeout**: 200 ms. **Retries**: up to 2.

### 2.3 `get_utility_signal`

- **Input**: `{}` (current-timestep signal only; no horizon parameter — kept deliberately simple for the PoC).
- **Output**: `{ "enabled": boolean, "carbon_intensity_gco2_kwh": number | null, "price_signal_relative": number | null }`. When `enabled: false` (the default unless a run config turns it on), both value fields are `null` and the agent's system prompt instructs it to ignore this signal entirely rather than treat `null` as "zero."
- **Errors**: none expected in the stub implementation; a production swap to a live feed would add `isError` cases for feed unavailability.
- **Timeout**: 200 ms. **Retries**: up to 2.

### 2.4 `compute_pmv`

- **Input**: `{ "air_temp_c": number, "mean_radiant_temp_c": number, "air_speed_ms": number, "rh_pct": number, "met_rate": number, "clo": number }`.
- **Output**: `{ "pmv": number, "ppd_pct": number }` computed via Fanger's model (Fanger, 1970; standardized in ISO 7730 and referenced by ASHRAE 55), with `ppd_pct = 100 − 95·exp(−0.03353·pmv⁴ − 0.2179·pmv²)`.
- **Errors**: `isError: true`, `{ "reason": "input_out_of_valid_range", "field": "..." }` if an input falls outside the model's documented applicability range (e.g., air speed and clothing/metabolic bounds per ASHRAE 55's elevated-air-speed method).
- **Timeout**: 50 ms (pure arithmetic). **Retries**: not needed — deterministic and near-instant; a failure means invalid input, not transient failure, so retrying unchanged input is pointless (the caller must fix the input instead).
- Called by the Bridge every zone timestep (§3 of `05_Runtime_Execution.md`), not only during agent decision cycles — this is why it is listed as a "pure compute" tool independent of the agent loop.

### 2.5 `propose_setpoints`

- **Input**: `{ "objective_weights": { "w_energy": number (0–1), "w_comfort_penalty": number (0–1) }, "horizon_steps": integer, "carbon_aware": boolean }`.
- **Output**: `{ "candidate": { "heating_c": number, "cooling_c": number, ... }, "predicted_kwh_horizon": number, "predicted_pmv_range": [number, number], "rationale_tags": ["string"] }` — `rationale_tags` are short machine-generated labels (e.g., `"cold_snap_forecast"`, `"peak_demand_avoidance"`) the LLM can quote back in its own explanation rather than needing to re-derive the reasoning from scratch.
- **Implementation**: the deterministic, bounded-horizon optimizer argued for in `06_Control_System.md` §2–3 — not an LLM call.
- **Errors**: `isError: true`, `{ "reason": "infeasible", "detail": "..." }` if no candidate satisfies the hard constraints (e.g., an extreme-weather day where even the widest allowed setpoint can't hold the hard comfort band — see `01_Requirements.md` Edge Cases) — this is a legitimate, expected outcome the agent must be able to see and report honestly, not an error to hide.
- **Timeout**: 1 s. **Retries**: up to 1 with a wider horizon relaxation, only if `infeasible`; otherwise not retried blindly.

### 2.6 `validate_action`

- **Input**: `{ "candidate": { "heating_c": number, "cooling_c": number, ... }, "cycle_id": "string" }`.
- **Output**: `{ "valid": boolean, "reasons": ["string"] }` — `reasons` is populated on failure with specific, actionable violations (e.g., `"cooling_c 17.5 below allow-listed minimum 18.0"`), so the agent's follow-up turn has something concrete to react to rather than a bare "no."
- **Implementation**: pure function against the config-loaded allow-list bounds (`03_Component_Design.md` §4) — no I/O, no randomness, exhaustively property-testable (`13_Testing.md`).
- **Errors**: none in the `isError` sense — a failed validation is a normal, successful call that returned `valid: false`; this is a deliberate design choice so "the action was rejected" is always visible to the agent as ordinary content, never swallowed as a protocol-level error.
- **Timeout**: 50 ms. **Retries**: not applicable (pure, deterministic).

### 2.7 `apply_setpoints`

- **Input**: `{ "action": { "heating_c": number, "cooling_c": number, ... }, "cycle_id": "string" }`.
- **Output**: `{ "committed": boolean, "applied_action": { ... }, "cycle_id": "string" }`.
- **Idempotency**: keyed on `cycle_id`. The server-side handler checks "has this `cycle_id` already been committed?" before calling `set_actuator_value` again; a repeat call with the same `cycle_id` and the same action returns `committed: true` without re-writing anything. A repeat call with the same `cycle_id` but a *different* action is rejected (`isError: true`, `{ "reason": "cycle_id_action_mismatch" }`) — this is a deliberate safety property: a `cycle_id` names one decision, not a mutable slot.
- **Server-side re-validation**: this tool independently re-checks the action against the same allow-list bounds `validate_action` uses, **even if the agent already called `validate_action` and got a pass** — the agent's own tool-calling sequence is never trusted as a substitute for the server enforcing its own invariants (this is the concrete mechanism behind `01_Requirements.md` SR-2 and the general "never trust the caller" principle stated in `04_Dataflow.md` §6).
- **Errors**: `isError: true` with `{ "reason": "out_of_bounds" }` (should be unreachable if `validate_action` was called first and passed, but is checked anyway), `{ "reason": "unknown_actuator" }`, `{ "reason": "cycle_id_action_mismatch" }`.
- **Timeout**: 500 ms. **Retries**: **not** retried automatically on transport failure/timeout (§4 of `04_Dataflow.md` explains why); the orchestrator instead calls `get_zone_state` afterward to observe the actual committed setpoint before deciding whether a follow-up call is needed.

### 2.8 `get_history`

- **Input**: `{ "query_type": "similar_conditions" | "recent_incidents" | "daily_summary", "params": { ... } }` — a small fixed set of query shapes, not a free-form query language, so the agent can't construct an expensive or unbounded scan.
- **Output**: shape depends on `query_type`, always bounded in size (e.g., `similar_conditions` returns at most the 5 most similar past days by a simple weather-similarity metric, never a raw dump).
- **Errors**: `isError: true`, `{ "reason": "no_comparable_history" }` — an expected, graceful outcome on cold start (`01_Requirements.md`, Edge Cases), not a failure.
- **Timeout**: 300 ms. **Retries**: up to 2.

### 2.9 `log_decision`

- **Input**: `{ "cycle_id": "string", "rationale": "string", "action_or_incident": { ... }, "trace": [ {"tool": "string", "args": {...}, "result_summary": "string"} ] }`.
- **Output**: `{ "logged": true }` (effectively always — see below).
- **Implementation**: enqueues onto the async Storage buffer described in `04_Dataflow.md` §3; the tool call itself returns immediately regardless of whether the underlying write has completed, by design, so a slow database can never add latency to the decision cycle.
- **Errors**: none surfaced to the agent — if the underlying async write ultimately fails, that is a Monitoring-level incident (`03_Component_Design.md` §11), not something the agent should have to reason about mid-cycle.

### 2.10 `raise_incident`

- **Input**: `{ "cycle_id": "string", "reason": "string", "severity": "info" | "warning" | "critical" }`.
- **Output**: `{ "acknowledged": true }`.
- **Effect**: triggers the fallback path (last known-good / scheduled value) at the Bridge level and records the incident for Monitoring; this is the tool the agent (or the orchestrator, on the agent's behalf, on timeout) calls when it cannot produce a validated action within the cycle's tool-call budget.

## 3. Security posture for this tool surface (summary; full threat model in `14_Security.md`)

- No tool grants shell access, file write, or arbitrary code execution — the entire agent capability surface is these ten tools (`01_Requirements.md`, SR-3).
- Every write tool (`apply_setpoints`, `log_decision`, `raise_incident`) is idempotent by `cycle_id`.
- `apply_setpoints` independently re-validates server-side rather than trusting a prior `validate_action` call (§2.7).
- Any free-text field returned by a tool that could plausibly originate outside this project's own trusted config/data files (in the PoC, effectively none — the weather/utility feeds are local file-derived stubs) would be treated as untrusted content per MCP's own annotation-trust guidance, not fed back into the agent's effective permission set.

## 4. What is deliberately not a tool

The agent has no tool to modify the actuator allow-list, no tool to change the comfort-band configuration, no tool to retrain or fine-tune anything, and no tool to restart or reconfigure the simulation. These are operator-level configuration decisions (`03_Component_Design.md` §10) and are out of the agent's reach by construction, not merely by convention.
