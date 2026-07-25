# Project Rules & Architectural Constraints — Eco-Loop Building Agents

This document defines the binding rules, invariants, and guardrails for implementing the Eco-Loop Building Agents system. All development must strictly adhere to these rules without alteration or unauthorized refactoring.

## Reference Specifications
- **Project Understanding:** [PROJECT_UNDERSTANDING.md](file:///c:/Users/tarun/Desktop/Eco-Loop%20Building%20Agents/PROJECT_UNDERSTANDING.md)
- **Implementation Review:** [IMPLEMENTATION_PLAN_REVIEW.md](file:///c:/Users/tarun/Desktop/Eco-Loop%20Building%20Agents/IMPLEMENTATION_PLAN_REVIEW.md)
- **Project Bible (Exhibit A):** [Exhibit A/](file:///c:/Users/tarun/Desktop/Eco-Loop%20Building%20Agents/Exhibit%20A)
- **Implementation Specs (Exhibit B):** [Exhibit B/](file:///c:/Users/tarun/Desktop/Eco-Loop%20Building%20Agents/Exhibit%20B)

---

## Conflict Precedence Rule
If architecture and implementation documentation ever disagree or if implementation convenience conflicts with a specification:
$$\mathbf{Architecture\ (Exhibit\ A)\ always\ wins}$$
Never optimize by violating architectural guardrails.

---

## 23 Architectural Guardrails (Absolute Rules)

### EnergyPlus Boundary
1. **Bridge is the only EnergyPlus interface.** No module outside `src/bridge/` imports `pyenergyplus` or calls into the EnergyPlus Runtime API.
2. **No direct EnergyPlus actuator writes outside Bridge.** `mcp_server/tools/apply_setpoints.py` delegates the actual write to `bridge/`; it does not call `pyenergyplus` directly.
3. **`.idf` editing and runtime control never call into each other.** `idf_tools/` (offline, via `eppy`) and `bridge/` (online, via the Actuator API) are separate mechanisms; there is no mid-run `.idf` hot-reload.

### Control Safety
4. **No component bypasses `validate_action`.** Every candidate action is validated before it can reach an actuator, regardless of the agent's stated confidence.
5. **`apply_setpoints` independently re-validates server-side**, even given a prior passing `validate_action` call in the same cycle — the agent's own call sequence is never trusted as sufficient by itself.
6. **The LLM never performs the numeric optimization itself.** `propose_setpoints` is a deterministic tool; the LLM weights objectives and interprets results, it does not compute setpoint arithmetic.
7. **The LLM never writes actuators directly.** All actuator writes are mediated by `apply_setpoints`, which itself only delegates to Bridge.
8. **PMV/PPD is always computed by the deterministic `compute_pmv` tool** (Fanger/ISO 7730) — never estimated by the LLM.
9. **Every actuator has a hard-coded, config-defined min/max bound**, independent of the LLM and independent of objective-weight configuration.
10. **On any validator rejection, agent failure, or timeout, the system holds the last known-good or `.idf`-scheduled value** — never an extrapolated "best guess."

### Agent Capability Boundary
11. **No shell tool, file-write tool, or code-execution tool is ever exposed to the agent.**
12. **The MCP tool list is fixed at exactly ten tools.** No dynamic tool registration; no agent-requested new tools.
13. **The agent cannot modify the actuator allow-list, comfort-band configuration, or its own tool set.** These are operator-level, config-time decisions.
14. **Raw simulation logs and raw historical telemetry never enter the LLM's context by default.** Only bounded, aggregated, on-demand query results do (`get_history`).

### Data Flow & Concurrency
15. **The decision loop is synchronous, in-callback, and bounded by a cycle-level timeout** (8s P95) — not queue-mediated.
16. **Storage writes are asynchronous (fire-and-forget) from the decision-cycle path.** A slow or failing Storage write must never add latency to, or block, the EnergyPlus callback.
17. **Every write tool (`apply_setpoints`, `log_decision`, `raise_incident`) is idempotent by `cycle_id`.**
18. **`apply_setpoints` is never blindly retried on transport failure or timeout.** A missing acknowledgment is not treated as "didn't happen."
19. **Every tool call, its arguments, and its result are logged with the `cycle_id` it belongs to**, whether the call succeeds or fails.

### Configuration & Architecture Integrity
20. **Runtime configuration is immutable after load.** No comfort band, actuator bound, decision cadence, or objective weight is mutated during a run.
21. **Dashboard is read-only.** No write path exists from Dashboard to Storage, Bridge, or Agent.
22. **The safety case for this entire system depends on operating against a simulation, never live equipment.**
23. **No architectural decision recorded in `17_Architecture_Decision_Records.md` (ADR-001 through ADR-012) is reversed by an implementation-phase change.**

---

## 15 Critical Invariants

1. `src/bridge/` is the sole importer of `pyenergyplus`.
2. No out-of-band actuator writes outside `src/bridge/` and `mcp_server/tools/apply_setpoints.py`.
3. Offline `.idf` modification only (`src/idf_tools/`); no runtime `.idf` editing.
4. `validate_action` must be invoked and passed before any actuator write.
5. `apply_setpoints` re-validates setpoints server-side.
6. Setpoint arithmetic is strictly performed by `propose_setpoints` solver.
7. No direct LLM actuator access.
8. Analytical Fanger PMV/PPD calculation via `comfort/pmv.py`.
9. Actuator min/max bounds loaded from configuration and immutable.
10. Fail-safe fallback (`hold_last_known_good`) on validation failure, tool error, or timeout.
11. Absolute prohibition of shell, file-write, or code-exec tools in MCP server.
12. Fixed 10-tool MCP catalog.
13. Immutable operational parameters at runtime.
14. Pull-not-push history access via `get_history` tool only.
15. Synchronous decision loop in EnergyPlus callback; asynchronous non-blocking storage queue for telemetry.
