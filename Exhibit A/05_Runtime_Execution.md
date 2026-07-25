# 05 — Runtime Execution

The complete execution cycle, start to finish, for one run (baseline or agent-driven — the only difference is a config flag, per FR-9 in `01_Requirements.md`).

## 1. Process startup

1. Config Loader reads and schema-validates the run config (comfort bands, cadence, actuator allow-list, model endpoint, `.idf`/`.epw` paths, `run_mode: baseline | agent`).
2. If `run_mode: agent`: the LLM Client checks the inference server is reachable (fail fast, not on cycle 1) and the MCP Server process is started/connected (stdio transport — a subprocess, per `09_MCP_Architecture.md`).
3. Storage opens (or creates) the embedded database file; schema migration runs if needed (idempotent — safe to run against an existing file).
4. The Bridge creates a fresh EnergyPlus state (`api.state_manager.new_state()`), registers its callbacks against the calling points it needs (see §3), and calls `request_variable` for every sensor the config declares (must happen before `run_energyplus` — this is a setup-time-only call per the API's own documented usage pattern).
5. The Bridge resolves every configured actuator's handle **lazily**, on first use inside a callback, gated on `api_data_fully_ready(state)` returning true — handles are not reliably resolvable before this point, so the Bridge does not attempt it during step 4.
6. `api.runtime.run_energyplus(state, args)` is called. Control now passes to EnergyPlus; everything from here happens inside EnergyPlus-driven callbacks until the run ends.

## 2. Warmup

EnergyPlus runs its warmup days (repeating the first days of the run period until the zone temperatures converge) before the "real" run period begins. The Bridge's callbacks fire during warmup too, but:

- Decision cycles (calls into the Agent Orchestrator) are **gated off** during warmup — checked via the exchange API's warmup/environment-kind indicators, not by the Bridge keeping its own day-counter, since EnergyPlus is the authority on simulation time and phase.
- `SensorSnapshot`s are still recorded during warmup for debugging visibility but are excluded from Analytics by a `phase: warmup` tag, so warmup noise never contaminates the reported kWh/comfort numbers.

## 3. The per-timestep loop

Two callback registrations do two different jobs, deliberately kept separate:

- **`callback_end_zone_timestep_after_zone_reporting`**: fires every zone timestep. The Bridge reads sensors, computes PMV, and pushes a `SensorSnapshot` — cheap, always-on bookkeeping.
- **A cadence check inside that same callback** (not a separate registration) determines whether *this* timestep is also a decision-cycle boundary (default: every 15 simulated minutes — configurable per NFR-3). If yes, and only then, the Bridge hands off to the Agent Orchestrator synchronously (per `02_Architecture.md` §1), with a bounded per-cycle timeout.
- Actuator commits happen in `callback_after_predictor_after_hvac_managers` when overriding an HVAC-managed setpoint node is required (the documented pattern for overriding a `SetpointManager`-controlled node is to actuate the node's own `System Node Setpoint`/`Temperature Setpoint` actuator directly — never the `SetpointManager` object itself — verified against current EnergyPlus API usage examples), so the override is visible to the HVAC managers that run afterward in the same timestep.

This "read every timestep, decide every N timesteps" split is why PR-3 in `01_Requirements.md` (an every-timestep annual AI-driven run) is explicitly not required: the *reads* stay cheap and full-resolution; only the *reasoning* is throttled, and it's the reasoning that's expensive.

## 4. One decision cycle, step by step

1. **Assemble** `ObservationContext`: latest `SensorSnapshot`, PMV/PPD, current setpoints, Memory's rolling window + reflection summary.
2. **Reason**: Agent Orchestrator sends this to the LLM with the fixed tool schema set. The LLM may request `get_weather_forecast`/`get_utility_signal`/`get_history` first; each round-trips through the MCP server.
3. **Propose**: the LLM calls `propose_setpoints` with objective weights it has decided on for this cycle (e.g., "weight comfort higher — forecast shows a cold snap").
4. **Validate**: the LLM (or the orchestrator, deterministically, if the LLM skips this step) calls `validate_action`. If it fails, the orchestrator does **not** silently retry the same candidate — it feeds the failure reason back to the LLM as a new tool result and gives it one more reasoning turn within the same cycle's tool-call budget (this is the system's only "self-correction" loop within a single cycle; cross-cycle self-correction is Memory's reflection mechanism, a different thing — see `08_LLM_and_Agent_System.md`).
5. **Commit or escalate**: pass → `apply_setpoints`, writes through the Bridge to the actuator. Fail (budget exhausted, still invalid, or any timeout) → `raise_incident`, and the Bridge re-asserts the last known-good/scheduled value.
6. **Log**: a `DecisionLog` (full trace: every tool call, every result, the final action or incident, latency) is enqueued asynchronously — this never blocks the timestep from proceeding.
7. **Return**: the Bridge's callback returns; EnergyPlus proceeds with the (possibly just-updated) actuator value in effect for this timestep's HVAC calculation.

## 5. Run-period end

- EnergyPlus reaches the end of the configured run period (or, for the PoC's representative-day strategy per PR-3, the end of the selected representative window) and the simulation completes normally.
- The Bridge flushes any buffered-but-not-yet-written telemetry (§3 of `04_Dataflow.md`) before releasing the EnergyPlus state.
- Analytics runs its aggregation pass over the just-completed run's data, tagged with `run_mode` and a `run_id`, producing a `RunSummary`.
- If this was the agent run and a baseline run for the same model/weather already exists (or vice versa), the Dashboard's comparison view becomes available; if only one side exists, the dashboard shows single-run metrics and flags the comparison as incomplete rather than fabricating a baseline.

## 6. Abnormal termination

- **Recoverable severe error** (EnergyPlus continues but flags a problem, e.g., a bad but non-fatal setpoint request from *EnergyPlus's own* internal logic, unrelated to our actuator writes): logged as a `phase: error_recovery` tagged event; the run continues; this is expected occasionally and is not itself a defect in this system.
- **Fatal error**: caught via the message/error-flag callback where the API surfaces it; the Bridge attempts to flush whatever telemetry is already buffered, marks the `RunSummary` as `incomplete`, and exits cleanly rather than leaving a corrupt/partial database write in progress — a partial, clearly-labeled result is preferred over a silent, ambiguous one.
- **Process killed externally** (e.g., during development, or a demo re-take): on restart, Storage's schema includes a `last_committed_cycle_id` per `run_id`; the Bridge/Agent Orchestrator do not need special resume logic for the *simulation* (EnergyPlus itself does not resume mid-run — a new run starts from the top), but the *data layer* is written so that a partial run's records are never double-counted if a retry happens to reuse a `run_id` (defense-in-depth; in practice each run attempt gets a fresh `run_id`, per §5 of `04_Dataflow.md`'s idempotency discussion).
