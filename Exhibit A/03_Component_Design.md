# 03 — Component Design

Each component below is specified as: **Responsibility**, **Interfaces** (what it exposes / consumes — schemas live in `12_API_Design.md` and `09_MCP_Architecture.md`), **Key design decisions**, and **Data owned**. No component owns data that another component also writes, to avoid the dual-writer problems that make `13_Testing.md`'s recovery tests necessary in the first place.

---

## 1. EnergyPlus Integration (the "Bridge")

- **Responsibility**: Own the entire relationship with the running EnergyPlus process — state creation, callback registration, sensor/actuator handle resolution, and translating raw exchange-API values into the typed `SensorSnapshot` the rest of the system uses. Nothing else in the system imports `pyenergyplus` directly.
- **Interfaces**: Registers itself against `api.runtime.callback_*` calling points at startup; internally calls `api.exchange.get_variable_value`/`get_actuator_handle`/`set_actuator_value`/`request_variable`; exposes `on_decision_cycle(snapshot, cycle_id) -> Action | None` to the Agent Orchestrator (an in-process synchronous call — see `02_Architecture.md`, §1).
- **Key design decisions**: (1) Gates on `api_data_fully_ready` before touching any handle (per the API's own documented behavior — handles are not reliably defined before this). (2) Resolves handles once and caches them (handle lookups are string-keyed and not meant to be repeated every timestep). (3) Distinguishes decision-cadence timesteps from every-timestep bookkeeping — sensor snapshot + PMV computation happen every zone timestep (cheap), but the Agent Orchestrator is invoked only on cadence boundaries (expensive; §5 of `05_Runtime_Execution.md`).
- **Data owned**: actuator handle table, the mapping from config-declared logical actuator names to EnergyPlus's `(component_type, control_type, key)` triples.

## 2. LLM Layer

- **Responsibility**: Abstract "talk to a model that can call tools" behind one interface, independent of whether the backend is Ollama, vLLM, or another OpenAI-compatible server. Owns prompt templates, tool-schema serialization, and constrained/structured-output configuration.
- **Interfaces**: `complete(messages, tools, response_format) -> Completion` (may contain text and/or tool calls); configuration for which decoding-constraint mechanism is active (native tool-calling vs. grammar-constrained JSON — see `08_LLM_and_Agent_System.md`, §5).
- **Key design decisions**: Static content (system prompt, tool schemas) is kept as a stable prefix across calls specifically to benefit from prefix/KV-cache reuse in the serving stack (`15_Performance.md`); only the growing observation/turn history is appended. Structured output is enforced at the decoder level (grammar/JSON-schema constraint), not by asking nicely in the prompt — constrained decoding removes syntax errors but not semantic errors, so this layer does not claim to remove the need for validation downstream.
- **Data owned**: none persisted; this is a stateless service wrapper. (Conversation state lives in Memory, below.)

## 3. Agent Layer (Orchestrator)

- **Responsibility**: Run the actual decision loop: assemble context from the current snapshot + memory, call the LLM, execute any tool calls it requests via the MCP client, and terminate the loop with either a validated committed action or an escalation.
- **Interfaces**: `on_decision_cycle` (from Bridge, synchronous); MCP client calls to the tool server; reads/writes Memory.
- **Key design decisions**: ReAct-style single-agent loop with a bounded tool-call budget per cycle (default 6), not a multi-agent or tree-search architecture — justified fully in `08_LLM_and_Agent_System.md`. A cycle-level timeout wraps the whole loop (not just the LLM call) so a slow tool or a runaway tool-call loop can't stall the simulation indefinitely.
- **Data owned**: the in-flight reasoning trace for the current cycle (discarded or summarized into Memory at cycle close, never left dangling).

## 4. Control Layer

- **Responsibility**: The two components that make the "deterministic core" real: the `propose_setpoints` optimizer and the `validate_action` gate. Deliberately separated from the Agent Layer so they can be tested, fuzzed, and reasoned about with zero LLM involvement.
- **Interfaces**: exposed only as MCP tools (`09_MCP_Architecture.md`); never called directly by the Bridge except for the FR-8 fallback path, which bypasses the optimizer entirely and just re-applies the last known-good value.
- **Key design decisions**: `validate_action` is pure and total — for any input it returns pass/fail, never throws, never blocks on I/O, so it can be property-tested exhaustively (`13_Testing.md`). `propose_setpoints` is deterministic given the same inputs (no hidden randomness) so its output is reproducible and debuggable.
- **Data owned**: the allow-listed actuator bound table (SR-1/SR-2 in `01_Requirements.md`); this table is config-loaded, not learned or LLM-editable.

## 5. Memory

- **Responsibility**: Give the agent enough context to act coherently across cycles without either (a) re-deriving everything from scratch every cycle or (b) growing the LLM context unboundedly over a multi-day run.
- **Interfaces**: `get_recent_window(n) -> [Turn]`, `get_reflection_summary() -> str`, `append(turn)`, `end_of_day_reflect()`.
- **Key design decisions**: Two tiers — a small rolling window of recent cycles kept verbatim in context, and a periodically (end-of-simulated-day) regenerated natural-language summary that replaces older turns rather than accumulating them, following the Reflexion pattern of converting outcomes into compact verbal lessons instead of raw transcript. Longer-horizon lookups ("how did we handle a day like this before") go through the `get_history` **tool** against the durable store — a query, not a context dump — so raw historical data never gets pushed into the prompt by default (this is the same "pull not push" pattern used for long simulation logs — see `15_Performance.md`, §2).
- **Data owned**: the rolling window and the current reflection summary (ephemeral, agent-process memory); the durable historical record itself is owned by Storage, not by this component.

## 6. Logging

- **Responsibility**: Structured, correlation-ID-threaded logs for every component, independent of the analytics/telemetry pipeline (logs are for debugging a run; analytics are for reporting on a run — different consumers, different retention needs).
- **Interfaces**: a thin structured-logging wrapper (standard library `logging` with a JSON formatter) used by all components; every log line includes `cycle_id` where applicable.
- **Key design decisions**: Logging calls from the Bridge's callback path are non-blocking (buffered/async handler) so a slow log sink cannot add latency to the EnergyPlus callback.
- **Data owned**: log files/streams; not queried by the dashboard (the dashboard reads Storage's structured tables, not log text).

## 7. Analytics

- **Responsibility**: Turn raw `SensorSnapshot`/`DecisionLog` rows into the specific comparison numbers `01_Requirements.md` requires: kWh totals, % reduction, PMV-band compliance %, both per-run and baseline-vs-agent.
- **Interfaces**: batch queries against Storage, run at simulation end (and optionally incrementally during a run for a live dashboard); outputs a small, fixed-schema `RunSummary` record (see `12_API_Design.md`).
- **Key design decisions**: Computed identically for baseline and agent runs from the same underlying table schema (FR-9/FR-10) — there is exactly one code path that computes "% PMV-band compliance," used for both runs, so the comparison can't silently diverge in methodology between the two.
- **Data owned**: derived/aggregated tables (materialized once per run, not recomputed live on every dashboard page load).

## 8. Dashboard

- **Responsibility**: Present the baseline-vs-agent comparison to a non-specialist reviewer (per the stakeholder persona in `00_Project_Overview.md`).
- **Interfaces**: reads only from Analytics' `RunSummary` and Storage's time-series tables; never talks to the live simulation or the LLM directly (the dashboard is a pure read-side consumer, so it can be opened, refreshed, or shared independent of whether a simulation is currently running).
- **Key design decisions**: static/local rendering is sufficient for the PoC deliverable (a report or a locally-served page); no requirement for multi-user access control since there's no multi-tenant concern in this phase (`01_Requirements.md`, assumption 6 in `00_Project_Overview.md`).
- **Data owned**: none — presentation only.

## 9. Storage

- **Responsibility**: Durable record of every `SensorSnapshot`, `DecisionLog`, and `RunSummary`, across baseline and agent runs, keyed so the two are comparable but not conflated.
- **Interfaces**: append-only writes from the Bridge (snapshots) and Agent Orchestrator (decisions), batch reads from Analytics/`get_history`.
- **Key design decisions**: full rationale in `11_Database_Design.md`; summary: embedded DuckDB (or SQLite) for the PoC, chosen over standing up InfluxDB/Postgres/Redis server processes that add operational surface without a corresponding benefit at this data volume, with TimescaleDB identified as the concrete production migration target.
- **Data owned**: the single source of truth for every metric reported anywhere else in the system.

## 10. Configuration

- **Responsibility**: Single source of truth for everything NFR-3 in `01_Requirements.md` requires to be externalized: comfort bands, decision cadence, actuator allow-list and bounds, objective weights, model/inference endpoint, and file paths.
- **Interfaces**: loaded once at process start by every component that needs it; validated against a schema at load time (fail fast on a bad config rather than fail confusingly mid-run) — this is exactly the "config file specifies an actuator not present in the loaded `.idf`" edge case from `01_Requirements.md` §12, caught here before the simulation starts.
- **Key design decisions**: one file, not scattered environment variables, so a full run configuration is a single reviewable artifact (also makes FR-9's "run the same model twice, baseline vs. agent" a one-flag difference in the same config, not two divergent code paths).
- **Data owned**: the config schema itself; runtime components treat it as read-only after load.

## 11. Monitoring

- **Responsibility**: Give a human watching a run (or the demo recording) visibility into whether the system is healthy right now — degraded mode, incident counts, current cycle latency — distinct from the after-the-fact Analytics/Dashboard.
- **Interfaces**: a minimal health/metrics surface (cycle latency, fallback-invocation count, LLM-reachability status) — for the PoC this can be as simple as a live-tailed structured log filtered to `level=INCIDENT`, with a documented upgrade path to a Prometheus-style metrics endpoint if this system's operational lifetime extends past the PoC.
- **Key design decisions**: monitoring is explicitly not conflated with logging (§6) — logging answers "what happened," monitoring answers "is it currently OK" — even though the PoC-scale implementation of both may share the same underlying log stream.
- **Data owned**: none beyond ephemeral counters; nothing here is relied upon for correctness, only for operator visibility.
