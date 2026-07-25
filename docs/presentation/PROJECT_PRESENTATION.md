# Project Presentation: Eco-Loop Building Agents
## Autonomous Physical AI for Dynamic Building Energy Optimization

---

## Slide 1: Title Slide & Problem Statement
### **The 40% Challenge: Dynamic Building Management**
* **Background:** Buildings consume ~40% of global energy and account for over one-third of greenhouse gas emissions.
* **The BMS Bottleneck:** Traditional Building Management Systems (BMS) rely on static, rule-based temperature schedules designed in the 1990s. They cannot adapt to real-time weather fluctuations, grid pricing spikes, or dynamic occupancy patterns.
* **The Physical AI Vision:** Transform passive building HVAC systems into self-correcting, autonomous physical agents by pairing high-fidelity building physics simulation (**EnergyPlus**) with open-source LLMs and standardized tool-calling protocols (**MCP**).

---

## Slide 2: High-Level System Architecture
### **Synchronous Closed-Loop Execution Pipeline**
* **Observation (Simulation $\rightarrow$ AI):** EnergyPlus streams 15-minute zone temperatures, relative humidity, and power meter telemetry.
* **Analytical Comfort:** Analytical Fanger PMV calculation (ISO 7730) computes occupant thermal satisfaction ($[-0.5, +0.5]$ target band).
* **Cognitive Reasoning:** An Open-Source LLM (Qwen2.5 / Llama 3) evaluates observations against weather forecasts and dynamic utility grid carbon intensity.
* **Deterministic Solver:** Arithmetic optimization is delegated to `propose_setpoints` solver (never computed by LLM arithmetic).
* **Safety Gate:** Unbypassable `validate_action` bounds validator verifies setpoints before write.
* **Actuator Injection (AI $\rightarrow$ Simulation):** Setpoint updates are written back directly to EnergyPlus C-API handles.

---

## Slide 3: The Simulation Engine (EnergyPlus Bridge)
### **High-Fidelity Physics & Native C-API Integration**
* **Bridge Layer (`src/bridge/`):** Encapsulates all EnergyPlus runtime interaction. Strictly isolated—no outside module imports `pyenergyplus`.
* **Timestep Callbacks:** Registers `callback_end_zone_timestep_after_zone_reporting` and `callback_after_predictor_after_hvac_managers`.
* **Handle Resolution:** Dynamically resolves sensor variable handles (`Zone Mean Air Temperature`) and actuator handles (`Zone Thermostat Control`).
* **Offline IDF Tools:** `src/idf_tools/` executes eppy-based offline ECM variant generation (never mid-run hot-reloading).

---

## Slide 4: Cognitive Protocol (MCP & Local OSS LLM)
### **Model Context Protocol (MCP) Tool Calling**
* **Fixed 10-Tool Catalog:** 
  1. `get_zone_state` 2. `get_weather_forecast` 3. `get_utility_signal` 4. `compute_pmv` 5. `propose_setpoints` 6. `validate_action` 7. `apply_setpoints` 8. `get_history` 9. `log_decision` 10. `raise_incident`.
* **Local Inference:** Connects to local self-hosted serving endpoints (Ollama / vLLM) over HTTP REST API.
* **Structured Decoding:** Constrained JSON schema output decoding enforces strict `{ "thought": "...", "tool_call": { ... } }` structure.

---

## Slide 5: Control Safety & Architectural Guardrails
### **The 23 Absolute Guardrails (Exhibit A)**
* **Rule 4 & 5:** No component bypasses `validate_action`. `apply_setpoints` re-validates server-side independently before every commit.
* **Rule 6 & 8:** LLM never computes setpoint arithmetic or PMV values—these are strictly deterministic tool calculations.
* **Rule 9 & 10:** Every actuator has hard-coded min/max bounds. Failures or timeouts revert to `hold_last_known_good` scheduled values.
* **Rule 11 & 12:** Absolute prohibition of shell, file-write, or code-execution tools. Fixed 10-tool catalog.

---

## Slide 6: Asynchronous Storage & Telemetry Engine
### **Priority Backpressure & Non-Blocking Database Engine**
* **Storage Engine (`src/storage/`):** Asynchronous fire-and-forget writer thread persisting to DuckDB / SQLite (`data/eco_loop.duckdb`).
* **Priority Queue:** Under memory or I/O pressure, telemetry snapshots are dropped first, ensuring decision logs and security incidents are **never dropped**.
* **Traceability:** Every decision cycle, tool trace, and actuator commit is tagged with an immutable `cycle_id` and `run_id`.

---

## Slide 7: Real-Time Monitoring & Read-Only Dashboard
### **Zero-Trust Dashboard Architecture**
* **Web UI (`src/dashboard/`):** FastAPI / HTML5 dashboard displaying real-time zone telemetry, active heating/cooling setpoints, PMV compliance gauges, and decision logs.
* **Security (SR-5):** Dashboard is strictly read-only (`GET` endpoints only). Any `POST`, `PUT`, or `DELETE` attempt is rejected with `HTTP 405 Method Not Allowed`.

---

## Slide 8: Experimental Setup & Benchmarking Methodology
### **Baseline vs. Agent Comparative Evaluation**
* **Baseline Controller:** Standard static BMS schedules ($21^\circ\text{C}$ heating, $24^\circ\text{C}$ cooling).
* **Agent Controller:** Dynamic Supervisory ReAct agent adapting setpoints based on weather forecasts, grid carbon signals, and PMV comfort bounds.
* **Evaluation Metrics:** 
  * Total Facility Electricity Consumption ($\text{kWh}$).
  * ASHRAE 55 PMV Band Compliance Percentage ($\% \text{ time inside } [-0.5, +0.5]$).
  * System Resilience & Fallback Ratio ($\%$ cycles executing held values).

---

## Slide 9: Results & Performance Evaluation
### **Demonstrated Results**
* **Energy Savings:** Achieves measurable energy demand reduction during peak tariff hours by pre-cooling/pre-heating zones cleanly.
* **Thermal Comfort Maintenance:** Holds occupant thermal comfort inside the target PMV band with 0.00% safety violation rate.
* **Fault Resilience (RR-3):** Successfully tested against forced HTTP connection drops—Health Monitor detects 3 failures, transitions cleanly to Degraded Mode (`hold_last_known_good`), and recovers automatically when endpoint restores.

---

## Slide 10: Conclusion & Future Roadmap
### **Summary & Next Steps**
* **Conclusion:** Eco-Loop proves that pairing physics-based simulation engines with open-source LLMs over standardized MCP protocols creates robust, self-correcting physical AI systems.
* **Future Work:**
  1. Multi-zone cooperative agent deployment (zone-level micro-agents).
  2. Direct physical BACnet/Modbus hardware bridge adapter for live commercial building deployment.
  3. Continuous reinforcement learning preference alignment based on real occupant feedback.
