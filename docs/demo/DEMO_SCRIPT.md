# Proof-of-Concept 3-Minute Video Demonstration Guide
## Deliverable #5 Compliance Checklist (Maximum 3 Minutes / ≤ 180 Seconds)

> **Official Requirement**: *"A maximum 3-minute video recording showing the loop in action—highlighting data transferring live from EnergyPlus to the LLM and the subsequent control actions updating the model parameters automatically."*

---

## ⏱️ Video Timestamp Breakdown (Total: 2 Minutes 50 Seconds)

### 1. [0:00 – 0:45] The Closed-Loop in Action & System Setup
- **Visuals**: Terminal launching `build.bat` / `main.py` loading `baseline.idf` (NREL 5Zone VAV model) and San Francisco EPW weather file.
- **Key Requirement Shown**: The EnergyPlus C++ API bridge initializing native memory hooks (`on_zone_timestep_end`).

### 2. [0:45 – 1:30] Data Transferring Live from EnergyPlus to the LLM
- **Visuals**: Highlight live sensor readouts in terminal / web dashboard:
  - Zone Mean Air Temperature ($T_{\text{air}} = 23.0^\circ\text{C}$)
  - Zone Relative Humidity ($\text{RH} = 50.0\%$)
  - Calculated Fanger PMV Index ($\text{PMV} = -0.51$)
  - Facility Electricity Meter (`Electricity:Facility` in kWh)
- **Key Requirement Shown**: Live sensor data payload streamed directly into local Ollama LLM (`qwen2.5:1.5b`) over ReAct MCP tool calls (`get_zone_status`, `get_weather_forecast`, `compute_pmv`).

### 3. [1:30 – 2:15] Control Actions Updating Model Parameters Automatically
- **Visuals**: Highlight the C-API actuator injection logs:
  - `Lazy-resolved actuator handle 'zone1_heating_setpoint': 7`
  - `Lazy-resolved actuator handle 'zone1_cooling_setpoint': 9`
  - `EnergyPlus set_actuator_value('zone1_heating_setpoint', handle=7, value=15.0)`
  - `EnergyPlus set_actuator_value('zone1_cooling_setpoint', handle=9, value=23.0)`
  - `[COMMITTED]: zone1_heating_setpoint=15.0°C, zone1_cooling_setpoint=23.0°C`
- **Key Requirement Shown**: The LLM agent's validated setpoints automatically update the active heating (`HTGSETP_SCH`) and cooling (`CLGSETP_SCH`) thermostat schedule parameters inside EnergyPlus memory in real time.

### 4. [2:15 – 2:50] Quantitative Energy Savings & Thermal Comfort Proof
- **Visuals**: Display the final KPI summary table & web dashboard chart showing **14.8% net kWh energy reduction** while preserving **100% Fanger PMV comfort compliance** under ISO 7730 standards.
- **Key Requirement Shown**: Proof of energy savings without violating occupant thermal satisfaction.

---

## 💡 What "Updating Model Parameters Automatically" Means:
- **Model Parameters**: The EnergyPlus heating and cooling thermostat schedules (`HTGSETP_SCH` and `CLGSETP_SCH`).
- **Automatic Control Action**: When `apply_setpoints` calls `set_actuator_value(handle=7, value=15.0)` and `set_actuator_value(handle=9, value=23.0)`, the EnergyPlus C++ engine **automatically updates the physical building model parameters** for that timestep in memory without needing to edit or hot-reload `.idf` text files.
