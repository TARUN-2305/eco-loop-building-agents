# Proof-of-Concept Video Demonstration Script
## Autonomous Physical AI Building Agent (3-Minute Storyboard)

---

## Technical Setup Before Recording
1. Start local LLM server: `ollama serve` (serving `qwen2.5:1.5b` on `http://localhost:11434/v1`).
2. Open terminal window 1: Ready to launch `python main.py --config configs/agent.yaml --mode agent --dashboard --port 8080`.
3. Open Web Browser: Navigated to `http://localhost:8080` (Real-Time Live Dashboard).

---

## Scene Breakdown & Voiceover Storyboard

### Scene 1: Introduction & Digital Twin Initialization (0:00 – 0:30)
* **Visuals:** 
  * Split-screen showing terminal window launching `main.py` and the EnergyPlus Bridge loading building model `baseline.idf` and weather file `USA_CA_San.Francisco.Intl.AP.724940_TMY3.epw`.
* **Voiceover:**
  > "Welcome to Eco-Loop: an autonomous physical AI system that optimizes commercial building energy efficiency and thermal comfort in real time. Buildings generate nearly 40% of global carbon emissions, yet traditional management systems rely on static, decades-old schedules. Today we demonstrate a live, closed-loop physical AI pipeline pairing the EnergyPlus physics engine with a local open-source LLM via the Model Context Protocol."

---

### Scene 2: Live Ingestion & Cognitive LLM Reasoning (0:30 – 1:15)
* **Visuals:** 
  * Zoom in on terminal logs showing `eco_loop.bridge.callbacks` ingesting zone temperatures, relative humidity, and power meter data.
  * Highlight real HTTP requests sent over MCP to local Ollama instance (`qwen2.5:1.5b`). Show the LLM invoking `get_weather_forecast` and `propose_setpoints`.
* **Voiceover:**
  > "Every 15 simulated minutes, EnergyPlus streams sensor telemetry to our Bridge via native C-API callbacks. The LLM Agent receives the current zone state alongside Fanger PMV thermal comfort metrics. It queries 24-hour weather forecasts and grid carbon signals over MCP. Notice that the LLM does not guess math—it invokes our deterministic setpoint solver tool to generate optimal heating and cooling candidates."

---

### Scene 3: Deterministic Safety Validation & Actuator Injection (1:15 – 2:00)
* **Visuals:** 
  * Show the MCP tool log for `validate_action` returning `valid: true`.
  * Highlight `apply_setpoints` re-validating setpoints server-side before committing values directly to EnergyPlus handles (`zone1_heating_setpoint: 201`, `zone1_cooling_setpoint: 201`).
* **Voiceover:**
  > "Safety is absolute in Eco-Loop. Before any candidate action reaches an actuator, it passes through an unbypassable safety gate. The validator verifies that setpoints respect hard comfort bounds and peak power limits. Once validated, `apply_setpoints` independently re-validates the payload server-side and injects updated setpoints back into EnergyPlus handles in real time."

---

### Scene 4: Self-Correction & Fault Resilience (2:00 – 2:30)
* **Visuals:** 
  * Temporarily simulate an LLM connection dropout in terminal. Show `HealthMonitor` detecting consecutive failures, logging an incident to DuckDB, and cleanly activating Degraded Mode (`hold_last_known_good`).
  * Restore connection and show automatic recovery back to NOMINAL status.
* **Voiceover:**
  > "Physical AI must be resilient. If an LLM endpoint drops or times out, our Health Monitor detects the failure after three cycles and seamlessly transitions to Degraded Mode. The building holds its last known-good schedule without dropping simulation frames, recovering automatically once connection restores."

---

### Scene 5: Quantitative Dashboard & Summary (2:30 – 3:00)
* **Visuals:** 
  * Switch to full screen of the Live Dashboard at `http://localhost:8080`.
  * Display real-time gauges showing PMV comfort compliance at 98.5%, total energy savings compared to baseline, and decision log tables.
* **Voiceover:**
  > "On the dashboard, we observe the continuous quantitative results: occupant thermal comfort is strictly maintained inside the ASHRAE 55 band while energy consumption is optimized dynamically. By combining high-fidelity physics engines, local open-source LLMs, and deterministic safety guardrails, Eco-Loop delivers true autonomous physical AI for smart buildings. Thank you."
