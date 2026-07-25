# Eco-Loop Building Agents — Honest Status Report

**Scope:** Independent audit of the repository against the Eco-Loop Building Agents hackathon brief and its stated Evaluation Criteria.
**Method:** Direct inspection of source, config, IDF/EPW inputs, stored benchmark data, and the project's own verification documents. Every claim below cites a file and, where relevant, a line number.

---

## Executive Verdict

The scaffolding is real: the EnergyPlus C-API bridge, the MCP tool catalog, the ReAct orchestrator, and the Fanger PMV solver are all legitimately implemented. **The closed loop they're supposed to form does not close.** The building model has no HVAC system to control, the configured actuators reference schedules that don't exist, sensor reads silently fall back to hardcoded constants, and the headline energy metric is a hardcoded number that never changes. The project's own `data/benchmark_results.json` shows both agent runs failing 100% of decision cycles — and the project's own verification reports claim the opposite for the same runs, on the same date.

Score against the rubric as currently submitted: **not passing on System Integration, Energy Efficiency, or Presentation & Documentation.** Comfort and Agentic Autonomy have real underlying work but cannot be scored honestly until the pipeline they depend on is fixed.

---

## 1. System Integration (30%) — FAILING

**Rubric question:** *"How robustly and reliably does the closed-loop pipeline execute without crashing over an extended simulation time horizon?"*

| Finding | Evidence |
|---|---|
| The base building model has no HVAC system at all | `data/idf/baseline.idf` contains zero `ZoneHVAC:*`, `ZoneControl:Thermostat`, `SetpointManager:*`, or `People` objects. Its only load objects are named `Test 352a` / `Test 352 minus` — a canonical NREL regression-test pair for validating the `OtherEquipment` object, not a building. |
| Configured actuators don't exist in the model | `configs/agent.yaml` declares actuators with `key: "CLGSETP_SCH"` and `key: "HTGSETP_SCH"`. Neither string appears anywhere in `data/idf/baseline.idf` (verified by direct grep). `get_actuator_handle()` will return `-1` for both, every run. |
| The two actuators are also cross-wired | `zone1_heating_setpoint` is bound to `CLGSETP_SCH` (a *cooling*-sounding name) under `control_type: "Heating Setpoint Schedule Value"`; `zone1_cooling_setpoint` is bound to `HTGSETP_SCH` under `control_type: "Cooling Setpoint Schedule Value"`. Backwards, independent of the missing-schedule problem. |
| Zone name mismatch breaks sensor reads | `src/bridge/lifecycle.py:122-123` and `src/bridge/handles.py:78,82` hardcode the zone key `"Zone1"`. The actual zone object in `baseline.idf` is named `ZONE ONE`. Variable handle lookups will fail. |
| The failure is silent for sensors (not for actuators) | `src/bridge/handles.py:79-84` — when `get_variable_handle()` returns `-1`, the code simply skips the read and keeps the pre-set default (`zone_temp = 23.0`, `zone_rh = 50.0`), with **no log line**. Actuator handle failures *are* logged (`handles.py:54-58`), but nothing downstream checks whether a "committed" action actually reached the physics engine. |
| Deliverable #2 (modified IDF variants) is missing | `data/idf/ecm_variants/` contains only `.gitkeep`. `src/idf_tools/ecm_sweep.py` exists but nothing has been generated into it. |
| Tests don't cover any of the above | 35/37 unit/integration tests pass locally; the 2 failures are solely `ModuleNotFoundError: pyenergyplus` (native binding not installed in this environment — expected, not a logic bug). No test asserts that a configured actuator key or zone name actually resolves against the shipped IDF. That's the coverage gap that let all four issues above ship together. |

**Net effect:** the pipeline runs, produces logs, and doesn't crash — but it is not controlling the building, because there is no controllable building underneath it.

---

## 2. Energy Efficiency Realized (25%) — UNMEASURABLE (currently fabricated)

**Rubric question:** *"The net reduction in energy use achieved by the autonomous agent compared to standard baseline scheduling."*

The entire metric traces to one line:

```python
# src/bridge/handles.py, line 119
meters = {"facility_electricity_kw": 25.0}
```

This is a hardcoded constant. A repo-wide search for `get_meter_handle` / `get_meter_value` / `Electricity:Facility` returns **zero hits** in `src/`. No code path ever reads a real EnergyPlus meter. Every consumer of this value — `src/analytics/kpi.py` (`total_kwh`), the dashboard, `RunSummary`, and both verification reports — inherits a number with no causal link to weather, occupancy, HVAC setpoints, or anything else the agent does.

Consequence visible in the data on disk (`data/benchmark_results.json`):
- Baseline run: `total_kwh: 0.0` — an office building consuming zero electricity over 24 hours is not physically meaningful.
- Agent runs: `total_kwh: 162.5` and `62.5` — these numbers move only because of run duration/cycle count bookkeeping, not because any actuator write changed a physical load.

**The hackathon's core requirement — "explicitly prove percentage reductions in total kWh consumed" — cannot currently be satisfied honestly**, regardless of how good the agent's decisions are, because the signal it's supposedly optimizing was never wired to the simulation.

---

## 3. Thermal Comfort & Constraints (20%) — Real engine, unverifiable output, contradicted by own data

**Rubric question:** *"Did the AI save energy at the expense of human occupant comfort, or did it intelligently balance both?"*

- `src/comfort/pmv.py` is a correct, self-contained Fanger / ISO 7730 implementation with proper input-bounds validation. This part is genuinely fine and doesn't depend on the IDF having a `People` object — a reasonable design choice.
- However, it's fed exclusively by the same broken sensor pipeline described in Section 1. Since zone temperature and RH silently fall back to constants (`23.0°C` / `50%`), the PMV values reported for real runs describe a fixed default, not the building.
- **Direct, checkable contradiction:** `data/benchmark_results.json` records `pmv_compliance_pct: 0.0` for *both* agent runs (`bench_agent_stub`, `bench_agent_degraded`). `docs/verification/06_BASELINE_VS_AGENT_REPORT.md`, dated the same day, reports **100.0% PMV Band Compliance** for the same two named runs. These cannot both be true; the raw JSON is the machine-generated ground truth and should be trusted over the narrated report.

---

## 4. Agentic Autonomy & Code Elegance (15%) — The strongest part of the project, but untested against reality

**Rubric question:** *"Effective and creative leverage of open-source LLM tool-calling capabilities, MCP protocols, and self-correction loops."*

What's genuinely good:
- `src/agent/orchestrator.py` implements a sensible ReAct loop: `propose_setpoints` → `validate_action` → `apply_setpoints`, with an independent server-side re-validation before any actuator write (`orchestrator.py:136-146`), a last-known-good fallback path, and a `HealthMonitor` that trips a degraded mode after repeated LLM failures.
- 10 MCP tools are registered and exercised (`propose_setpoints`, `validate_action`, `apply_setpoints`, `get_zone_state`, `get_weather_forecast`, `get_utility_signal`, `get_history`, `compute_pmv`, `log_decision`, `raise_incident`).
- `src/agent/llm_client.py` targets a real OpenAI-compatible / Ollama-style HTTP endpoint — this is not mocked in the production code path.

The gap: `commit_actuator()` in `src/bridge/handles.py:170-184` records the action as successfully committed and updates `_last_known_good_values` **even when the resolved handle is `-1`** — i.e., a decision cycle can be logged as `"outcome": "committed"` while nothing was written to EnergyPlus at all. The orchestrator has no mechanism to distinguish a real commit from a no-op one. Combined with Section 1's findings, this means "agentic autonomy" cannot currently be demonstrated as *effective* — only as *executed*.

The one benchmark run on file used a stub LLM (`bench_agent_stub`) and recorded `consecutive_llm_failures: 3`, `degraded_mode_active: true` — the agent never completed a clean decision cycle in the data provided.

---

## 5. Presentation & Documentation (10%) — Actively misleading in its current state

**Rubric question:** *"Clarity of the system architecture design, data visualizations, and project delivery."*

- **No `README.md` exists at the repository root.** (The only README found is an auto-generated one inside `.pytest_cache`, which is not part of the project.)
- The repo contains **~3,300 lines** of planning/audit documents (Exhibit A: 17 files, Exhibit B: 10 files, plus `IMPLEMENTATION_PLAN_REVIEW.md` and `PROJECT_UNDERSTANDING.md`) against **~3,280 lines** of actual source and **~1,070 lines** of tests — roughly a 1:1 planning-to-code ratio, plus 11 additional "verification report" files layered on top.
- `IMPLEMENTATION_PLAN_REVIEW.md` and the `docs/verification/` reports audit **internal document consistency** (dependency graphs, a traceability matrix claiming "100% requirements coverage," 12 ADRs cross-checked) — none of which caught the functional bugs in Sections 1–3, because none of them checked the planning documents against the actual IDF, config, or benchmark data.
- **The single highest-risk finding for judges:** `docs/verification/11_FINAL_ACCEPTANCE_REPORT.md` self-certifies:
  > "Overall Verification Completeness: 100.0% (35/35 tests passing)... Live Demo Readiness: GO (100% Ready)... Sign-off: Approved for Live Demonstration and Research Release."

  dated the same day as `data/benchmark_results.json`, which shows 100% fallback rate and 0% comfort compliance for both agent runs on record. This is trivially checkable by any judge who opens both files, and it undermines every other claim in the documentation set by association.
- `docs/demo/DEMO_SCRIPT.md` narrates specific actuator handle values (e.g. "zone1_heating_setpoint: 201") that are illustrative placeholders, not values derived from an actual successful run — because, per Section 1, no run on file has successfully resolved those handles at all.

---

## Quick Reference — File:Line Index of Every Finding

| # | Issue | Location |
|---|---|---|
| 1 | No HVAC/thermostat/People objects in building model | `data/idf/baseline.idf` (entire file) |
| 2 | Actuator keys reference nonexistent schedules | `configs/agent.yaml` (actuators block) |
| 3 | Heating/cooling actuator keys swapped | `configs/agent.yaml` (actuators block) |
| 4 | Hardcoded zone name `"Zone1"` vs real `"ZONE ONE"` | `src/bridge/lifecycle.py:122-123`, `src/bridge/handles.py:78,82,110` |
| 5 | Silent fallback on sensor read failure | `src/bridge/handles.py:76-86` |
| 6 | Hardcoded fake energy meter | `src/bridge/handles.py:119` |
| 7 | Commit succeeds even when actuator handle is -1 | `src/bridge/handles.py:170-184` |
| 8 | Empty ECM variants deliverable | `data/idf/ecm_variants/` |
| 9 | No README | repo root |
| 10 | Verification report contradicts raw benchmark data | `docs/verification/06_BASELINE_VS_AGENT_REPORT.md` vs `data/benchmark_results.json` |
| 11 | Final acceptance report contradicts raw benchmark data | `docs/verification/11_FINAL_ACCEPTANCE_REPORT.md` vs `data/benchmark_results.json` |
