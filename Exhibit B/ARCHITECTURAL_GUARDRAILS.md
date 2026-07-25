# ARCHITECTURAL_GUARDRAILS.md

These rules are absolute. They are not implementation guidance to be balanced against convenience — a change that violates one of these is a Project Bible violation, not a refactor, and should be rejected in code review regardless of who proposes it or why. Each rule names the document(s) it originates from. If a future need genuinely conflicts with one of these, the correct action is to amend the Project Bible explicitly (a new ADR, a stated contradiction resolution) — never to quietly work around the rule in code.

## EnergyPlus Boundary

1. **Bridge is the only EnergyPlus interface.** No module outside `bridge/` imports `pyenergyplus` or calls into the EnergyPlus Runtime API. *(02_Architecture.md §3.1; ADR-002; 07_EnergyPlus_Design.md)*
2. **No direct EnergyPlus actuator writes outside Bridge.** `mcp_server/tools/apply_setpoints.py` delegates the actual write to `bridge/`; it does not call `pyenergyplus` itself. *(02_Architecture.md §3.1; 09_MCP_Architecture.md §2.7)*
3. **`.idf` editing and runtime control never call into each other.** `idf_tools/` (offline, via `eppy`) and `bridge/` (online, via the Actuator API) are separate mechanisms; there is no mid-run `.idf` hot-reload. *(07_EnergyPlus_Design.md §4)*

## Control Safety

4. **No component bypasses `validate_action`.** Every candidate action is validated before it can reach an actuator, regardless of the agent's stated confidence. *(FR-6; 06_Control_System.md §4; 09_MCP_Architecture.md §2.6)*
5. **`apply_setpoints` independently re-validates server-side**, even given a prior passing `validate_action` call in the same cycle — the agent's own call sequence is never trusted as sufficient by itself. *(09_MCP_Architecture.md §2.7; SR-2)*
6. **The LLM never performs the numeric optimization itself.** `propose_setpoints` is a deterministic tool; the LLM weights objectives and interprets results, it does not compute setpoint arithmetic. *(06_Control_System.md §1.5, §2; ADR-005)*
7. **The LLM never writes actuators directly.** All actuator writes are mediated by `apply_setpoints`, which itself only delegates to Bridge. *(09_MCP_Architecture.md §2.7; ADR-005)*
8. **PMV/PPD is always computed by the deterministic `compute_pmv` tool** (Fanger/ISO 7730) — never estimated by the LLM. *(FR-3; ADR-010)*
9. **Every actuator has a hard-coded, config-defined min/max bound**, independent of the LLM and independent of objective-weight configuration. *(SR-1)*
10. **On any validator rejection, agent failure, or timeout, the system holds the last known-good or `.idf`-scheduled value** — never an extrapolated "best guess." *(SR-4; FR-8)*

## Agent Capability Boundary

11. **No shell tool, file-write tool, or code-execution tool is ever exposed to the agent.** *(SR-3; 14_Security.md §5; ADR-011)*
12. **The MCP tool list is fixed at exactly ten tools.** No dynamic tool registration; no agent-requested new tools; adding an eleventh tool requires an explicit Project Bible amendment first, not a silent code change. *(09_MCP_Architecture.md §2; SR-3)*
13. **The agent cannot modify the actuator allow-list, comfort-band configuration, or its own tool set.** These are operator-level, config-time decisions, never runtime-mutable by the agent. *(09_MCP_Architecture.md §4)*
14. **Raw simulation logs and raw historical telemetry never enter the LLM's context by default.** Only bounded, aggregated, on-demand query results do (`get_history`). *(15_Performance.md §3; 08_LLM_and_Agent_System.md §3)*

## Data Flow & Concurrency

15. **The decision loop is synchronous, in-callback, and bounded by a cycle-level timeout** — not queue-mediated. *(02_Architecture.md §1; ADR-007)*
16. **Storage writes are asynchronous (fire-and-forget) from the decision-cycle path.** A slow or failing Storage write must never add latency to, or block, the EnergyPlus callback. *(04_Dataflow.md §3; ADR-007)*
17. **Every write tool (`apply_setpoints`, `log_decision`, `raise_incident`) is idempotent by `cycle_id`.** *(09_MCP_Architecture.md §2.7/§2.9/§2.10)*
18. **`apply_setpoints` is never blindly retried on transport failure or timeout.** A missing acknowledgment is not treated as "didn't happen." *(04_Dataflow.md §4; RR-2)*
19. **Every tool call, its arguments, and its result are logged with the `cycle_id` it belongs to**, whether the call succeeds or fails. *(FR-12; 09_MCP_Architecture.md §2.9)*

## Configuration & Architecture Integrity

20. **Runtime configuration is immutable after load.** No comfort band, actuator bound, decision cadence, or objective weight is mutated during a run — a different configuration is a new run, not a live change. *(NFR-3; 03_Component_Design.md §10)*
21. **Dashboard is read-only.** No write path exists from Dashboard to Storage, Bridge, or Agent. *(03_Component_Design.md §8)*
22. **The safety case for this entire system depends on operating against a simulation, never live equipment.** Nothing in this codebase is to be connected to real HVAC hardware without a new, explicit safety review — this Project Bible does not certify that connection as safe. *(SR-5; 00_Project_Overview.md §3.2)*
23. **No architectural decision recorded in `17_Architecture_Decision_Records.md` is reversed by an implementation-phase change.** A perceived improvement during implementation is evaluated as a potential Project Bible amendment (a new or superseding ADR), never applied silently in code while the documentation still describes the old decision.

## How these are enforced, not just stated

| Guardrail category | Enforcement mechanism |
|---|---|
| EnergyPlus Boundary (1–3) | Directory structure (`REPOSITORY_STRUCTURE.md`) + an import-linter/CI rule forbidding `pyenergyplus` imports outside `bridge/` |
| Control Safety (4–10) | `validator/`'s property-based fuzz suite; `apply_setpoints`'s server-side re-check; code review checklist in `CODE_QUALITY_GUIDE.md` |
| Agent Capability Boundary (11–14) | CI check asserting exactly ten registered tools (SR-3); MCP server code review — no tool implementation may shell out or write arbitrary files |
| Data Flow & Concurrency (15–19) | Architecture review of `agent/orchestrator.py`'s call graph; idempotency unit tests per write tool |
| Configuration & Architecture Integrity (20–23) | Config object designed as immutable after construction (no setters); pull-request review requiring an explicit ADR reference for any change touching a documented decision |

## What happens if a guardrail and a deadline conflict

If implementation pressure ever makes violating one of these rules look like the fastest path to a working demo, the correct response is to **surface the conflict explicitly** — document it as a risk (`16_Risk_Register.md`-style entry) or an amendment proposal — not to quietly ship the violation. A demo that works by bypassing `validate_action`, for instance, is not a working demo of this project; it is a different, unspecified project that happens to share a codebase.
