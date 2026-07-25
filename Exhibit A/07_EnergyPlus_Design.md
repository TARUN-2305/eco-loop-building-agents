# 07 — EnergyPlus Design

This document is the technical grounding for the integration choice argued in `02_Architecture.md` §3.1. Facts here are verified against NREL/DOE's current EnergyPlus Python API documentation (the "latest" branch tracks EnergyPlus 26.2 at time of writing) and current community usage patterns, not assumed from general familiarity with the tool — the API has evolved release over release and this project depends on getting the current shape right.

## 1. The three API surfaces

`EnergyPlusAPI()` exposes three child objects, each with a distinct job:

- **`api.runtime`** — registers Python callbacks against named points in the simulation lifecycle, and starts the simulation itself (`run_energyplus`).
- **`api.exchange`** — the "data transfer" surface used *inside* a callback: resolve a handle once (`get_variable_handle`, `get_actuator_handle`, `get_meter_handle`), then repeatedly read (`get_variable_value`, `get_actuator_value`, `get_meter_value`) or write (`set_actuator_value`) using that handle. A handle lookup by string is not free; resolving it once and caching it is standard practice and is what this project's Bridge does (`03_Component_Design.md` §1).
- **`api.functional`** — static, state-independent calculations (psychrometrics, glycol properties) that don't require a running simulation; used here to fill in any comfort-model inputs not directly exposed as a sensor.

An important, easy-to-miss detail from the API's own documentation: many of these functions are **not reliably defined until `api.exchange.api_data_fully_ready(state)` returns true.** Handle resolution and any read/write attempted before that point can silently misbehave. The Bridge therefore treats "am I past `api_data_fully_ready`" as a hard gate before touching any handle, using a one-time-then-cached pattern inside the first callback invocation rather than trying to resolve handles at setup time.

## 2. Callback points actually used

| Registration | Purpose in this system |
|---|---|
| `callback_end_zone_timestep_after_zone_reporting` | Primary hook: read sensors, compute PMV, decide whether this is a decision-cycle boundary. Fires after zone reporting so the timestep's final values are settled. |
| `callback_after_predictor_after_hvac_managers` | Where actuator commits happen when overriding an HVAC-managed setpoint node, so the override takes effect for HVAC managers that run in this same timestep rather than being one timestep late. |
| `callback_begin_new_environment` / warmup indicators | Used to gate decision cycles off during warmup and sizing environments (`01_Requirements.md`, Edge Cases). |
| `callback_message` | EnergyPlus's mechanism for surfacing warnings/errors as they're printed; used for the recoverable-vs-fatal distinction in `05_Runtime_Execution.md` §6. |
| `callback_progress` | Optional — feeds the Monitoring component (`03_Component_Design.md` §11) a percentage-complete signal, useful for the demo recording. |

The API documentation is explicit that this registration pattern — "create a callback function in Python, and register it... to allow the callback to be called at a specific point in the simulation," with sensor/actuator access available inside that callback — is the intended usage; nothing here is an unsupported or fragile use of the library.

## 3. Actuators: how set-point override actually works

A common mistake (visible repeatedly in EnergyPlus community troubleshooting threads) is trying to actuate a `SetpointManager` object directly. That does not work: EnergyPlus's actuator model does not expose "override this manager's output" as a concept. **The correct pattern is to actuate the downstream node's own actuator** — for example, the `System Node Setpoint` / `Temperature Setpoint` actuator on the specific supply-air outlet node — which overrides the value the setpoint manager would otherwise have written to that node, or equivalently to actuate the `Schedule Value` of a `Schedule:Compact`/`Schedule:Constant` object if the setpoint is schedule-driven. `get_actuator_handle` takes three identifying pieces — component type, control type, and a key naming the specific node/object instance — precisely because a component can have more than one control type available for actuation. This project's actuator allow-list (`01_Requirements.md`, SR-2) is expressed at exactly this level of specificity: not "the zone's setpoint" abstractly, but the concrete `(component_type, control_type, key)` triple, resolved and validated against the loaded `.idf` at startup so a misconfigured allow-list fails fast rather than silently doing nothing at runtime.

Once set, an actuator stays in the "externally overridden" state until explicitly reset (there is a corresponding reset call), which is exactly the property the fallback path (FR-8) relies on for "hold the last known-good value": the Bridge does not need to keep re-asserting a value every timestep if nothing has changed — although in practice this project re-asserts explicitly on every cycle for auditability (每 decision cycle's log clearly shows what was in effect and why), rather than depending on an implicit "it just stayed that way" behavior.

## 4. `.idf` modification: two genuinely different mechanisms, not one

The brief's language ("modified .idf versions generated throughout runtime evaluation") is easy to misread as "the running simulation edits its own input file." That is not how EnergyPlus works, and this spec resolves the ambiguity explicitly:

- **`eppy`-based `.idf` editing** happens **offline, before a simulation run starts** — it is a batch/text-generation tool for producing a *new* `.idf` variant (e.g., an ECM sweep: different insulation levels, different HVAC system types, different baseline schedules). Each variant becomes its own, separate, full simulation run. This is how FR-11 ("ECM sweep") is satisfied.
- **Runtime, within-run control** happens exclusively through the Actuator API described in §3, against the **one** `.idf` that was loaded for that run. There is no mechanism, and no need for one, to rewrite the `.idf` text mid-run — the whole point of the Actuator/EMS mechanism is to give an external program live control without ever touching the input file again after simulation start.

Confusing these two would be a real design error (e.g., trying to "hot reload" a modified idf mid-run, which EnergyPlus does not support), so this project's Bridge and its documentation keep them in clearly separate code paths: an offline `ecm_sweep.py`-class script using `eppy`, and the always-running Bridge using only the Actuator API.

## 5. EMS and the Python Runtime API's relationship

EMS (Energy Management System, EnergyPlus's built-in Erl scripting facility) and the external Python Runtime API are two different ways of driving the **same underlying actuator/sensor mechanism** — they are not competing systems with different capabilities, they are two different *languages* for the same capability. This project uses the Python Runtime API (external, general-purpose, network- and library-capable) rather than Erl (internal, `.idf`-embedded, cannot make an HTTP call to an LLM), for the reasons given in `02_Architecture.md` §3.1. This project therefore has no `EnergyManagementSystem:*` objects in its `.idf` at all — everything EMS would have done is done instead by the external Bridge script.

## 6. FMU / BCVTB: why neither is used here, and what they're actually for

- **BCVTB** (Building Controls Virtual Test Bed) is genuinely valuable middleware, maintained by LBNL, for coupling EnergyPlus's envelope/loads simulation to an **independent simulator** — classically, an HVAC or controls model built in Modelica/Dymola — via a Ptolemy-II-based socket protocol. It solves "how do two different simulation programs exchange data every timestep," which is not this project's problem: the thing on the other end of our data exchange is a decision-making agent, not another physics simulator.
- **EnergyPlusToFMU** (LBNL) packages EnergyPlus itself as a Functional Mock-up Unit, so a *different* master simulator (Modelica, Simulink) can drive it. Again, solves a different problem than "an LLM agent needs to read state and write setpoints."
- **Spawn-of-EnergyPlus**, DOE's next-generation engine, is the one to watch longer-term: it reuses EnergyPlus's envelope/loads modules but re-implements HVAC and controls in the equation-based Modelica language for fully dynamic (rather than EnergyPlus's quasi-steady-state) simulation, leaning on FMI internally for its own component coordination. If this project's control problem ever needed finer-grained HVAC dynamics than EnergyPlus's native timestep model provides, Spawn — not BCVTB, not a hand-rolled FMU — would be the natural upgrade path. Not needed for this PoC's scope.

## 7. Known limitations, stated plainly

- **No mid-run `.idf` hot-reload** (§4) — by design, not a bug to work around.
- **Minimum timestep granularity is coarser than "real-time HVAC control"** — sub-hourly timesteps (commonly 10–15 minutes, configurable down to a documented minimum) are the norm; this shapes the decision-cadence choice in `05_Runtime_Execution.md` (a decision every timestep is neither necessary nor, at LLM-inference latency, affordable — see `15_Performance.md`).
- **Handle/actuator availability is model-dependent** — which actuators exist depends entirely on what HVAC objects the loaded `.idf` defines; this project's config-time validation (checking the allow-list against actually-resolvable handles before the run starts) exists specifically because this is a real, easy way for a configuration to be silently wrong otherwise.
- **Wall-clock cost of a full annual run scales with model complexity**, and — separately and more significantly for this project — **wall-clock cost of an AI-driven run scales with how often the (comparatively slow) LLM reasoning step is invoked**, not with EnergyPlus's own speed. This is precisely why this spec adopts a representative-day sampling strategy for the AI-driven run rather than an every-timestep full-annual run (`01_Requirements.md`, PR-3).
- **Calling-point timing matters**: reading or writing at the wrong callback point can mean a value is stale (read before it's updated this timestep) or ineffective (written after the component that would have used it has already run). The specific calling points chosen in §2 are chosen for this reason, not arbitrarily.

## 8. Best practices this design follows

1. Resolve handles once, lazily, gated on `api_data_fully_ready` — never re-resolve every timestep.
2. Keep `.idf` editing (`eppy`, offline) and runtime control (Actuator API, online) in separate code paths that never call into each other.
3. Actuate the specific downstream node/schedule, never attempt to override a manager object.
4. Treat warmup and sizing environments as distinct simulation phases that the control loop must explicitly detect and exclude, not assume away.
5. Pin the EnergyPlus version this project is built and tested against, and re-verify actuator/variable names against the *actual* loaded `.idf` at startup rather than assuming names from one model transfer unchanged to another (this is exactly the kind of assumption `01_Requirements.md` §12's edge case — "config file specifies an actuator not present in the loaded `.idf`" — is designed to catch early).
