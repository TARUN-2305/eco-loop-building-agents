# 04 — Dataflow

This document enumerates the concrete messages, calls, and transitions that `02_Architecture.md`'s sequence diagram summarizes. Field-level schemas for MCP tool calls are in `09_MCP_Architecture.md`; this document is about *what flows where and why*, not the wire format.

## 1. Message / record types

| Type | Produced by | Consumed by | Persisted? |
|---|---|---|---|
| `SensorSnapshot` | Bridge, every zone timestep | PMV computation (immediately), Storage (async), Agent Orchestrator (on cadence boundaries, as the latest snapshot) | Yes — every timestep, not just decision cycles, so post-hoc analysis has full resolution even though decisions happen less often |
| `ForecastWindow` | `get_weather_forecast` tool | Agent Orchestrator (in-context only) | No (derivable from the EPW/forecast source on demand; not worth storing) |
| `UtilitySignal` | `get_utility_signal` tool | Agent Orchestrator | Optional — stored only if a run configuration enables carbon/price awareness |
| `ObservationContext` | Agent Orchestrator, assembled per decision cycle from `SensorSnapshot` + `ForecastWindow` + Memory | LLM (as prompt content) | No — ephemeral per-cycle input |
| `ToolCall` / `ToolResult` | LLM (call) / MCP server (result) | Agent Orchestrator loop | Yes, as part of `DecisionLog.trace` |
| `CandidateAction` | `propose_setpoints` tool | `validate_action` tool, then Agent Orchestrator | Only if it becomes a `DecisionLog` (i.e., always logged, whether it passed or failed validation) |
| `ValidationResult` | `validate_action` tool | Agent Orchestrator | Yes, inside `DecisionLog` |
| `ActuatorCommit` | `apply_setpoints` tool → Bridge | EnergyPlus (via `set_actuator_value`) | Yes, inside `DecisionLog` |
| `Incident` | `raise_incident` tool, or any caught fault | Monitoring, Storage | Yes |
| `DecisionLog` | Agent Orchestrator, once per cycle | Storage (async), Analytics | Yes — the canonical record of "what the AI did and why" |
| `RunSummary` | Analytics, at run end (or incrementally) | Dashboard | Yes |

## 2. Every API call in the loop

| Call | Direction | Sync/Async | Notes |
|---|---|---|---|
| `api.exchange.get_variable_value(state, handle)` | Bridge → EnergyPlus | Sync (in-callback) | One per sensor per timestep |
| `api.exchange.get_actuator_value(state, handle)` | Bridge → EnergyPlus | Sync | Used to read back current committed value (for "last known-good" fallback) |
| `api.exchange.set_actuator_value(state, handle, value)` | Bridge → EnergyPlus | Sync | Only on a validated commit or a fallback re-assertion |
| `api.exchange.request_variable(...)` | Bridge → EnergyPlus | Sync, setup-time only | Called once before `run_energyplus`, not per timestep |
| `tools/call compute_pmv` | Bridge → MCP Server | Sync | Every timestep (cheap, deterministic) |
| `tools/call get_weather_forecast` | Agent → MCP Server | Sync, retryable | Cadence-boundary only |
| `tools/call get_utility_signal` | Agent → MCP Server | Sync, retryable | Cadence-boundary only, only if enabled |
| `tools/call propose_setpoints` | Agent → MCP Server | Sync | Cadence-boundary only |
| `tools/call validate_action` | Agent → MCP Server | Sync, non-retryable-but-idempotent (pure function) | Always called before `apply_setpoints` |
| `tools/call apply_setpoints` | Agent → MCP Server → Bridge | Sync, idempotent via `cycle_id` | Not blindly retried (§4 below) |
| `tools/call get_history` | Agent → MCP Server → Storage | Sync, retryable | Optional, agent-initiated |
| `tools/call log_decision` / internal `DecisionLog` append | Agent → Storage | **Async, fire-and-forget** | The one call in this list that is deliberately non-blocking — see §3 |
| LLM `complete(...)` | Agent → LLM Inference Server | Sync, bounded timeout | The dominant latency cost (`15_Performance.md`) |

## 3. Why exactly one queue exists, and where

Per `02_Architecture.md` §1, the decision-making path is synchronous by design — EnergyPlus is already blocking on the Bridge's callback, so there is no benefit to adding a queue in that path, only added complexity and a new failure mode (what happens if the queue backs up?).

The **one** place a queue (or queue-like async buffer) exists is between "anything that produces a durable record" (snapshots, decision logs, incidents) and Storage. This is implemented as a bounded in-memory buffer with a background writer thread/task:

- Writes are enqueued and the caller returns immediately (fire-and-forget, per `SensorSnapshot` and `DecisionLog` in §1).
- The buffer is bounded; if Storage falls behind (disk contention, lock wait), the buffer applies backpressure by dropping the *oldest* buffered snapshot-level telemetry first (high-frequency, lower-value-per-record) while never dropping a `DecisionLog` or `Incident` (low-frequency, high-value-per-record) — this priority is a deliberate, stated trade-off, not an accident of implementation.
- This queue exists specifically so that a slow or momentarily failing database **cannot** propagate latency or failure back into the EnergyPlus callback (RR-4 in `01_Requirements.md` depends on this).

## 4. Idempotency and retries, precisely

- **Read-only tools** (`get_weather_forecast`, `get_utility_signal`, `get_history`, `compute_pmv`): safe to retry freely; RR-2 caps this at 2 retries with backoff before falling back, purely to bound cycle latency, not because retrying is unsafe.
- **`validate_action`**: pure function of its input; "retrying" it is meaningless (same input, same output) — if it fails, the agent either revises the candidate and calls it again with a *different* input, or the cycle escalates.
- **`apply_setpoints`**: the only call in the system with a real side effect on the simulation. It is idempotent **with respect to `cycle_id`**: calling it twice with the same `cycle_id` and the same action is a no-op the second time (the Bridge checks "have I already committed this `cycle_id`?" before calling `set_actuator_value` again). It is deliberately **not** blindly retried on transport failure, because a transport failure after the actuator write already succeeded, but before the acknowledgment reaches the agent, would otherwise cause a second, potentially different, write under retry logic that assumed "no response = didn't happen."

## 5. State transitions, consolidated

`02_Architecture.md` gives the Agent Orchestrator and Simulation Lifecycle state diagrams. The table below is the same transitions expressed as data — useful for `13_Testing.md`'s state-machine-coverage tests.

| From | Event | To |
|---|---|---|
| Idle | decision cadence elapsed | Observing |
| Observing | snapshot + memory assembled | Reasoning |
| Reasoning | LLM requests a tool | ToolCalling |
| ToolCalling | tool result returned | Reasoning |
| Reasoning | LLM emits candidate action | Proposing |
| Reasoning | timeout or malformed output | Escalating |
| Proposing | `validate_action` called | Validating |
| Validating | pass | Committing |
| Validating | fail | Escalating |
| Committing | `apply_setpoints` acked | Logging |
| Escalating | `raise_incident` called | FallbackControl |
| FallbackControl | last known-good applied | Logging |
| Logging | `DecisionLog` enqueued | Idle |

## 6. Cross-cutting: what never crosses which boundary

Stated explicitly because it's a security and reliability property, not just a style choice (see `14_Security.md` for the threat-model framing of the same facts):

- Raw `pyenergyplus` handles never leave the Bridge process/module — the Agent Orchestrator and MCP tools only ever see the typed `SensorSnapshot`/`CandidateAction` records, never a raw handle integer.
- The LLM never receives a tool that can call `set_actuator_value` directly — only `apply_setpoints`, which is validated first by construction of the loop (the agent *can* choose to skip calling `validate_action`, which is why `apply_setpoints` itself also re-checks against the bound table server-side before committing — never trust the caller to have done the right thing first).
- Raw historical telemetry never enters the LLM's context by default — only `get_history`'s aggregated/filtered response does, on request (`15_Performance.md`, §2).
