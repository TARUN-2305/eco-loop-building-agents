# 01 — Requirements

Inherits scope, assumptions, and constraints from `00_Project_Overview.md`. Every requirement below is written to be testable — see `13_Testing.md` for how each is actually verified.

---

## 1. Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | The system SHALL run an EnergyPlus simulation of a specified `.idf`/`.epw` pair under external programmatic control via the Python Runtime API (not headless-only). |
| FR-2 | The system SHALL read, at minimum, zone air temperature, zone relative humidity, a CO₂ or ventilation-adequacy proxy where the model supports it, HVAC electric/gas meter values, and current setpoints, once per configured decision cadence (default: every 15 simulated minutes; see `05_Runtime_Execution.md`). |
| FR-3 | The system SHALL compute Predicted Mean Vote (PMV) and Predicted Percentage Dissatisfied (PPD) per ASHRAE 55 / Fanger's model from simulation-derived inputs (air temperature, mean radiant temperature, air speed, relative humidity, plus configured metabolic rate and clothing insulation), deterministically — not via LLM estimation (rationale: `10_Machine_Learning.md`, §4). |
| FR-4 | The system SHALL present current state, forecast, and relevant history to an LLM agent through a defined MCP tool surface (`09_MCP_Architecture.md`), and SHALL NOT permit the agent to read or write simulation state through any channel outside that tool surface. |
| FR-5 | The agent SHALL reason over the objectives configured for the run (comfort band, peak-demand threshold, carbon-intensity awareness where enabled) and produce a candidate control action: a set-point/schedule-value change, expressed as an explicit, typed proposal (not free text). |
| FR-6 | Every candidate action SHALL pass through a deterministic validator (`validate_action`, `09_MCP_Architecture.md`) before it is allowed to reach an actuator, regardless of the agent's own confidence or reasoning. |
| FR-7 | Validated actions SHALL be applied to the running EnergyPlus simulation via the Actuator API within the same or next decision cycle, and the applied value SHALL be logged with the full rationale text and a unique `cycle_id`. |
| FR-8 | If no action is validated (agent failure, timeout, or validation rejection) for a given cycle, the system SHALL fall back to the last known-good actuator value or, absent one, the `.idf`'s own scheduled value — never leave an actuator in an undefined state. |
| FR-9 | The system SHALL support running the identical building model twice — once under baseline (schedule-only, no agent) control and once under agent control — with both runs producing directly comparable logged metrics. |
| FR-10 | The system SHALL produce, at run end, an aggregated report/dashboard: total kWh (baseline vs. agent), % reduction, and comfort-band compliance (baseline vs. agent), computed identically for both runs. |
| FR-11 | The system SHALL support at least one full ECM (Energy Conservation Measure) sweep by generating modified `.idf` variants offline (via `eppy`) distinct from, and not to be confused with, the within-run actuator control loop (see `07_EnergyPlus_Design.md`, §4, for why these are two different mechanisms). |
| FR-12 | The system SHALL log every tool call, its arguments, its result (including errors), and the decision cycle it belongs to, in a form a human can review after the run (supports FR-13 and the "self-correction" rubric criterion). |
| FR-13 | The system SHALL expose a way to inspect *why* a given control action was taken (rationale text tied to `cycle_id`), not only *what* action was taken. |

## 2. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | **Maintainability**: each component in `03_Component_Design.md` SHALL be independently testable with the others mocked (enforced by the MCP boundary and the dependency graph in `02_Architecture.md`). |
| NFR-2 | **Portability**: the system SHALL run on Linux and macOS without code changes (EnergyPlus, Ollama/vLLM, and the chosen DB all support both); Windows is not a target for the PoC. |
| NFR-3 | **Configurability**: comfort bands, decision cadence, ECM bounds, and objective weights SHALL be externalized to a single config file, not hard-coded (supports re-running against a different building without a code change). |
| NFR-4 | **Observability**: every component SHALL emit structured (JSON) logs with a correlation ID (`cycle_id`) threading sensor read → reasoning → validation → actuation → persistence. |
| NFR-5 | **Reproducibility**: given the same `.idf`, `.epw`, config, and (where the inference stack supports it) a fixed sampling seed/temperature=0, two runs SHALL produce the same sequence of tool calls for a deterministic-mode demo recording (LLM sampling variance is otherwise expected and is not treated as a defect — see `13_Testing.md`, Regression). |

## 3. Performance Requirements

| ID | Requirement | Target | Rationale |
|---|---|---|---|
| PR-1 | Wall-clock time added per decision cycle by the AI loop (sensor read → PMV → LLM reasoning incl. tool calls → validation → actuation), P95 | ≤ 8 s on the reference hardware profile (mid-range single GPU, 7–14B model, quantized) | Derived in `15_Performance.md` from published local-inference throughput; a full simulated day at 15-minute cadence = 96 cycles, so 8 s/cycle ≈ 13 minutes of added wall-clock per simulated day — acceptable for a PoC demo. |
| PR-2 | Full-annual (8760 h) baseline run, no AI loop | Should complete in well under an hour on the reference hardware (EnergyPlus alone is fast); this is the *baseline* comparison run and is not latency-constrained by the AI loop. |
| PR-3 | Full-annual AI-driven run at every-timestep decision cadence | **Explicitly not required.** At PR-1's latency, an every-timestep annual run is impractical (see `07_EnergyPlus_Design.md`, "known limitations" and `16_Risk_Register.md`, R-04). The accepted approach is a **representative-day sampling strategy**: a small set of design days / representative weeks spanning the shoulder, peak-heating, and peak-cooling conditions, run under full AI control, with the annual baseline computed separately at full fidelity. This is stated as a requirement, not hidden as a limitation. |
| PR-4 | Dashboard render time after a completed run | ≤ 5 s for a full representative-day dataset | Ordinary web-app expectation; not a bottleneck given DuckDB/SQLite's analytical query speed (`11_Database_Design.md`). |

## 4. Reliability Requirements

| ID | Requirement |
|---|---|
| RR-1 | A single LLM tool-call failure (timeout, malformed output, connection error) SHALL NOT crash the simulation; it SHALL trigger the fallback path (FR-8) and be logged as an incident. |
| RR-2 | The system SHALL retry idempotent, read-only tool calls (e.g., `get_weather_forecast`) up to 2 times with backoff before falling back; it SHALL NOT blindly retry the non-idempotent `apply_setpoints` call without a `cycle_id`-based idempotency check (rationale: double-application risk — see `09_MCP_Architecture.md`). |
| RR-3 | If the LLM inference server becomes unreachable for more than a configured threshold (default: 3 consecutive cycles), the system SHALL enter a documented **degraded mode**: continue the simulation under the fallback controller only, log a persistent incident, and continue attempting reconnection in the background — it SHALL NOT abort the simulation run. |
| RR-4 | An EnergyPlus fatal error SHALL be caught via the `callback_message`/error-flag mechanism where possible, and the run SHALL terminate gracefully with partial results persisted, rather than losing all data from the run. |
| RR-5 | The system SHALL be restartable: on process restart, it SHALL resume logging against the last-committed `cycle_id` rather than silently overwriting or duplicating records (supports `13_Testing.md`, Recovery testing). |

## 5. Safety Requirements

| ID | Requirement |
|---|---|
| SR-1 | Every actuator the agent can write to SHALL have a hard-coded min/max bound, defined independently of the LLM and independently of the objective-weight configuration, informed by both comfort-safety and equipment-safety physics (e.g., supply-air setpoint bounded away from dew point and away from coil-freeze risk — see `14_Security.md`, §3, for the concrete bound-setting method). |
| SR-2 | No actuator write SHALL be permitted for any component/control-type/key combination not on an explicit allow-list configured for the run — an LLM proposal referencing an unlisted actuator SHALL be rejected by the validator, not attempted. |
| SR-3 | The agent SHALL NOT be given any tool that grants shell access, arbitrary file write, or arbitrary code execution. All capability is mediated through the fixed MCP tool set (`09_MCP_Architecture.md`). This is a explicit rejection of a common insecure PoC pattern — see `14_Security.md`, §5. |
| SR-4 | On any validator rejection or agent failure, the system SHALL prefer the safest known state (last known-good or `.idf`-scheduled value) over any extrapolated or "best guess" value. |
| SR-5 | This system's entire safety case rests on operating against a **simulation**, never live equipment (see `00_Project_Overview.md`, §3.2). SR-1 through SR-4 are still enforced as if real equipment were at risk, precisely so that the architecture does not have to change if it is ever connected to one — but no requirement in this document should be read as certifying this system safe for real-hardware deployment. |

## 6. Energy Constraints

| ID | Requirement |
|---|---|
| EC-1 | The agent's objective function SHALL include total facility energy (kWh) as a term to minimize, computed from EnergyPlus meter output, not estimated. |
| EC-2 | Where a peak-demand threshold is configured, the agent SHALL treat exceeding it as a constraint violation to avoid, not merely a cost to minimize (i.e., weighted heavily enough in the objective, and checked explicitly by the validator when a threshold is configured). |
| EC-3 | Where a carbon-intensity signal is enabled (stubbed for the PoC per `00_Project_Overview.md`), the agent MAY use it to prefer load-shifting within the comfort band, but EC-1/EC-2 remain binding regardless of carbon signal availability. |

## 7. Comfort Constraints

| ID | Requirement |
|---|---|
| CC-1 | Target band: PMV within **±0.5** during occupied hours (ASHRAE 55 general/Category-A-equivalent criterion, PPD ≤ 10%). |
| CC-2 | Hard band: PMV within **±1.5** at all times during occupied hours — the validator SHALL reject any proposed action whose predicted effect would push PMV outside this band, even if it would reduce energy. This tiered structure follows ISO 7730's graduated categories (±0.5 / ±0.7 / ±1.0 for its three comfort classes) by treating ±0.5 as the target and a wider band as an explicit, monitored tolerance rather than a silent failure. |
| CC-3 | Unoccupied hours are exempt from CC-1/CC-2 by default (setback is expected and desired) unless the configured objective explicitly requires otherwise (e.g., pre-conditioning before occupancy). |

## 8. Latency Requirements

Covered fully in `15_Performance.md`; summarized here as acceptance thresholds:

| ID | Requirement |
|---|---|
| LR-1 | P95 end-to-end decision-cycle latency ≤ 8 s (reference hardware; see PR-1). |
| LR-2 | LLM time-to-first-token, using prefix/prompt caching across cycles (static system prompt + tool schemas cached; only new observations appended), SHALL be measurably lower than a cold-context baseline — verified once during setup, not required to be re-verified every run. |
| LR-3 | Tool-call round-trip (agent → MCP server → tool implementation → response) excluding LLM think time SHALL be ≤ 200 ms P95 for all deterministic tools (`compute_pmv`, `validate_action`, `get_history` against a bounded window). |

## 9. Scalability

| ID | Requirement |
|---|---|
| SC-1 | The architecture SHALL NOT hard-code assumptions that prevent running N > 1 buildings (e.g., building identifiers threaded through all storage keys and tool calls from day one), even though only one building is run in the PoC. |
| SC-2 | Scaling to multiple simultaneous buildings SHALL be achievable by running multiple independent OS processes (one EnergyPlus + Bridge + Agent stack per building) sharing a common MCP server and LLM inference endpoint — not by re-architecting the per-building loop. This is a design constraint on `02_Architecture.md`, not a feature built in this phase. |

## 10. Failure Conditions

Enumerated so `13_Testing.md`'s fault-injection plan has concrete targets:

1. LLM inference server unreachable / connection refused.
2. LLM returns malformed JSON / an unparseable tool call.
3. LLM returns a syntactically valid but semantically out-of-bound action (e.g., setpoint outside allow-listed range).
4. LLM call exceeds latency budget (hang / very slow decode).
5. EnergyPlus emits a severe (recoverable) warning mid-run.
6. EnergyPlus emits a fatal error mid-run.
7. Database write fails (disk full, lock contention).
8. Two decision cycles attempt to apply actions concurrently (should not happen by design, but must fail safe if it does — see idempotency in `09_MCP_Architecture.md`).
9. Process is killed and restarted mid-run.
10. Config file specifies an actuator not present in the loaded `.idf`.

## 11. Acceptance Criteria

Direct restatement of `00_Project_Overview.md` §7 (S1–S7) as pass/fail gates for this specification:

- **A1** (= S1, S2): Extended run (≥ 1 representative simulated day at full cadence) completes with ≥ 99% of cycles clean and 0 fatal aborts attributable to the AI loop.
- **A2** (= S3, S4, S5): Agent-driven run shows positive kWh reduction vs. baseline AND comfort-band compliance ≥ baseline's own compliance.
- **A3** (= S6): < 5% of cycles in a nominal run invoke the fallback controller.
- **A4** (= S7): All 18 Project Bible documents present and cross-referenced.
- **A5**: Every failure condition in §10 has a corresponding fault-injection test in `13_Testing.md` with an observed, not merely claimed, graceful-degradation outcome.

## 12. Edge Cases

| Case | Handling |
|---|---|
| Simulation warmup period (before convergence) | Decision cycles SHALL NOT fire during EnergyPlus's warmup days; the Bridge gates on the simulation being past warmup (via the `warmup_flag`/environment-kind exchange calls — see `07_EnergyPlus_Design.md`). |
| Design-day vs. run-period environments | The system SHALL be able to distinguish which "environment" (per EnergyPlus's environment-index concept) it is in and SHALL only apply agent control during the intended run-period environment(s), not during sizing design days. |
| Extreme/out-of-design weather in the EPW | The validator's hard bounds (SR-1) apply unconditionally; the agent may be unable to hold the target comfort band on truly extreme days, and the system SHALL report this transparently rather than silently relaxing the bound. |
| Daylight-saving or schedule-boundary transitions in the weather file | Handled by EnergyPlus itself; the Bridge does not need special-case logic beyond reading `current_time`/`zone_time_step_number` from the exchange API each callback rather than keeping its own clock. |
| Cold start (first cycle of a run, no history) | `get_history`-dependent reasoning (e.g., "similar past conditions") SHALL degrade gracefully to "no comparable history" rather than erroring. |
| Occupancy = 0 for an extended stretch (holiday) | Setback logic applies (CC-3); the agent is not required to hold CC-1 during these periods. |

## 13. Out-of-Scope Items

Restated from `00_Project_Overview.md` §3.2 for completeness of this requirements document: real BMS/hardware integration, multi-building deployment, formal safety certification, live external weather/carbon feeds (stubbed instead), sub-second real-time control, personalized occupant comfort modeling, and any model training/fine-tuning. None of these are requirements this system is expected to meet, and none should be inferred from a requirement elsewhere in this document.
