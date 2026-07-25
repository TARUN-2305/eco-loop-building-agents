# Eco-Loop Building Agents — Remediation Plan

Companion to `REPORT.md`. Same structure, same rubric categories, one fix per finding. Priority 0 items block everything else — nothing in Priority 1–3 produces a trustworthy number until Priority 0 is done.

---

## Priority 0 — Unblock the loop

### Fix 1: Replace the building model
`data/idf/baseline.idf` is a regression-test fixture, not a building. Swap it for a real reference model with actual HVAC.

- Use one of NREL's standard reference building IDFs (Commercial Reference Buildings / DOE prototype buildings — e.g. a Small Office or Medium Office model). These already use the `CLGSETP_SCH` / `HTGSETP_SCH` schedule naming convention your `configs/agent.yaml` was clearly written against, so the actuator config needs minimal editing once the file is swapped.
- Before wiring anything else, verify the new file actually contains what your config expects:
  ```bash
  grep -n "CLGSETP_SCH\|HTGSETP_SCH" data/idf/baseline.idf
  grep -n "^\s*Zone,\|ZoneHVAC\|ZoneControl:Thermostat\|People," data/idf/baseline.idf
  ```
  All four greps should return matches before you proceed to Fix 2.
- Update `configs/agent.yaml` and `configs/baseline.yaml` `idf_path` if the filename changes, and fix the swapped `key` values so `zone1_heating_setpoint` actually points at the heating schedule and `zone1_cooling_setpoint` at the cooling schedule.

### Fix 2: Fix the zone name mismatch
Replace the hardcoded `"Zone1"` literal with the real zone name, sourced from config rather than hardcoded twice in two files.

```python
# configs/agent.yaml — add:
simulation:
  primary_zone_name: "ZONE ONE"   # or whatever the real IDF calls it
```

```python
# src/bridge/lifecycle.py — replace hardcoded "Zone1":
self._api.exchange.request_variable(self._state, "Zone Mean Air Temperature", self.config.simulation.primary_zone_name)
self._api.exchange.request_variable(self._state, "Zone Air Relative Humidity", self.config.simulation.primary_zone_name)
```

```python
# src/bridge/handles.py — same substitution in read_sensor_snapshot():
temp_handle = api.exchange.get_variable_handle(state, "Zone Mean Air Temperature", config.simulation.primary_zone_name)
rh_handle = api.exchange.get_variable_handle(state, "Zone Air Relative Humidity", config.simulation.primary_zone_name)
```

### Fix 3: Read the real energy meter
Replace the hardcoded constant with an actual EnergyPlus meter read.

```python
# src/bridge/handles.py — add during handle resolution (resolve_handles_if_ready):
self._meter_handle = api.exchange.get_meter_handle(state, "Electricity:Facility")

# in read_sensor_snapshot(), replace:
# meters = {"facility_electricity_kw": 25.0}
# with:
facility_kwh = 0.0
if self._meter_handle and self._meter_handle != -1:
    facility_kwh = api.exchange.get_meter_value(state, self._meter_handle)  # Joules, accumulated
meters = {"facility_electricity_kw": facility_kwh}
```
Note: `get_meter_value` returns accumulated Joules since last reset — convert to kW or kWh consistently with how `analytics/kpi.py` expects it, and confirm the meter resets on the cadence you assume (per-timestep vs cumulative).

### Fix 4: Fail loudly instead of silently
Two changes, both defensive:

```python
# src/bridge/handles.py, resolve_handles_if_ready() — after the actuator loop:
missing = [act.logical_name for act in config.actuators if act.logical_name not in self._actuator_handles]
if missing:
    raise RuntimeError(f"Cannot start run: unresolved actuator handles for {missing}. "
                        f"Check that config keys match objects in the loaded IDF.")
```

```python
# src/bridge/handles.py, read_sensor_snapshot() — replace the silent skip with a warning at minimum:
if temp_handle == -1:
    logger.error(f"Zone temperature variable handle unresolved for zone '{config.simulation.primary_zone_name}' — using stale default.")
```

```python
# src/bridge/handles.py, commit_actuator() — don't report success on a no-op write:
if handle == -1:
    logger.error(f"Cannot commit '{logical_name}': actuator handle never resolved.")
    return False
```
This last one is important: right now a "committed" decision can be a complete no-op. After this change, `commit_actuator` returning `True` actually means EnergyPlus received the write.

---

## Priority 1 — Make the numbers trustworthy

### Fix 5: Re-run and regenerate benchmark data honestly
Once Fixes 1–4 are in, re-run both `configs/baseline.yaml` and `configs/agent.yaml` over the full representative period already configured (`2026-07-01:2026-07-03`), and overwrite `data/benchmark_results.json` with real output. Do not hand-edit this file — it should only ever be produced by the runner.

### Fix 6: Rewrite the verification reports from the regenerated data
Every number in `docs/verification/*.md` should cite where it came from — a specific `run_id`, a specific DuckDB/SQLite query, or a specific line in `benchmark_results.json`. Suggested header block for each report:

```markdown
> **Data source:** `data/benchmark_results.json`, keys `baseline` / `agent_clean`, generated by `python main.py --config configs/{baseline,agent}.yaml` on <date>. Re-derive with: `SELECT ... FROM sensor_snapshots WHERE run_id = '<run_id>'`.
```
If a metric can't be traced to a query or a file, don't publish it as fact — mark it as a target or a limitation instead. Keep the old reports around (e.g. rename to `06_BASELINE_VS_AGENT_REPORT_v1_STUB.md`) rather than deleting — a documented "we caught this and fixed it" trail is worth more to judges than silence.

### Fix 7: Populate the ECM variants deliverable
Run `src/idf_tools/ecm_sweep.py` against the *new* baseline IDF to actually generate variant files into `data/idf/ecm_variants/` (deliverable #2 requires this — currently only `.gitkeep` is present).

---

## Priority 2 — Tests that would have caught this the first time

### Fix 8: Add a model/config consistency test
This single test would have caught 3 of the 4 root-cause bugs before they ever reached a live run:

```python
# tests/integration/test_idf_config_consistency.py
import eppy
from eppy.modeleditor import IDF

def test_actuator_keys_exist_in_idf(config, idd_path):
    idf = IDF(config.simulation.idf_path)
    schedule_names = {obj.Name.upper() for obj in idf.idfobjects.get("SCHEDULE:COMPACT", [])}
    for act in config.actuators:
        assert act.key.upper() in schedule_names, (
            f"Actuator '{act.logical_name}' references key '{act.key}' "
            f"which does not exist in {config.simulation.idf_path}"
        )

def test_primary_zone_exists_in_idf(config, idd_path):
    idf = IDF(config.simulation.idf_path)
    zone_names = {z.Name.upper() for z in idf.idfobjects.get("ZONE", [])}
    assert config.simulation.primary_zone_name.upper() in zone_names
```
Run this as a pre-flight check in `main.py` before invoking `bridge.run()`, not just in CI — it's cheap and catches config/model drift immediately.

### Fix 9: Assert handle resolution in the fault-injection suite
Add a test under `tests/fault_injection/` that deliberately points config at a nonexistent schedule name and asserts the system now raises (per Fix 4) rather than silently degrading — this turns today's accidental failure mode into a verified, intentional one.

---

## Priority 3 — Documentation and delivery hygiene

### Fix 10: Add a real top-level README.md
Minimum contents: what the system does, how to run baseline vs. agent mode, hardware/software prerequisites (EnergyPlus version + install path, Ollama model), and a **known limitations** section — judges respond better to an honest limitations list than to a discovered contradiction.

### Fix 11: Right-size Exhibit A/B relative to the code
Either trim these to the sections that actually informed implementation decisions, or add one line at the top of each: *"This is a planning artifact. See `docs/verification/` for evidence of what was actually built and measured."* Don't let document-consistency checks (traceability matrix, ADR cross-references) stand in for functional verification in the final submission.

### Fix 12: Re-record the demo video last
Only after Fix 5 produces a real, reproducible run should the 3-minute demo video be recorded. Show the actual `apply_setpoints` handle IDs and actual `total_kwh` delta from that run — not illustrative placeholder numbers.

---

## Definition of Done, mapped back to the rubric

| Criterion | Weight | Done when... |
|---|---|---|
| System Integration | 30% | A full representative-day run (baseline and agent) completes end-to-end with all actuator/variable handles resolved at startup (Fix 4's check passes); any fallback in the resulting log is attributable to a deliberate fault-injection test, not an unplanned failure. |
| Energy Efficiency Realized | 25% | `total_kwh` is sourced from `Electricity:Facility` (Fix 3); baseline vs. agent run over identical weather/occupancy shows a genuine, reproducible delta with a % reduction you can recompute from `benchmark_results.json` yourself. |
| Thermal Comfort & Constraints | 20% | PMV compliance is computed from real zone temp/RH/MRT reads (Fix 2), reported side-by-side with the energy delta so the comfort/energy tradeoff is visible, not just the savings number. |
| Agentic Autonomy & Code Elegance | 15% | The decision log shows a full propose → validate → apply trace for a real committed action (Fix 4 confirms it wasn't a no-op); degraded-mode fallback is demonstrated via a deliberate LLM-outage fault-injection test rather than appearing as an unplanned failure in the primary dataset. |
| Presentation & Documentation | 10% | A real README exists; every number in every verification report cites its source run/query (Fix 6); no report claims a status contradicted by `data/benchmark_results.json`. |

## Suggested Sequencing

1. **Fixes 1–4** (building model, zone name, meter, fail-fast) — this is the only work that changes whether the loop is real.
2. **Fix 5** — re-run and regenerate data.
3. **Fixes 6–7** — rewrite docs against real data, populate ECM variants.
4. **Fixes 8–9** — add the regression tests so this can't silently regress again.
5. **Fixes 10–12** — README, doc right-sizing, re-record video, in that order, last.

Don't reverse this order — recording the video or polishing the verification reports before Fix 1–4 land just produces a nicer-looking version of the same non-functional loop.
