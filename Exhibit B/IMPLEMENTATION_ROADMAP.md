# IMPLEMENTATION_ROADMAP.md

Every stage below builds only on what a prior stage has already produced. No stage requires a component from a later stage — this is verified explicitly in the Final Review at the bottom of this document. Complexity ratings are relative (Low/Medium/High), not calendar time; calendar time-boxing is `DEVELOPMENT_SEQUENCE.md`'s job. Risk references (R-xx) are IDs from `16_Risk_Register.md`.

---

## Stage 1 — Foundation

**Objective**: a repository that installs cleanly, validates its own configuration, and runs CI — before any simulation, agent, or storage code exists.

**Prerequisites**: none.

**Components to build**: repository scaffold (`REPOSITORY_STRUCTURE.md`); `config/` (schema + loader, per `12_API_Design.md` §3); pinned environment (Python version, EnergyPlus version per ADR-002, dependency lockfile); CI skeleton (lint + unit test runner on push).

**Expected outputs**: a config file that validates successfully against the schema; a deliberately broken config (missing LLM endpoint in `agent` mode, or an actuator name not checked against any `.idf` yet) rejected with a clear error; CI green on an empty test suite.

**Validation criteria**: config schema covers every field named in `01_Requirements.md` NFR-3 and `12_API_Design.md` §3; CI runs on both target OSes (NFR-2).

**Estimated complexity**: Low.

**Potential implementation risks**: R-08 (EnergyPlus version drift) begins here — the version pinned in this stage is the version every later stage assumes.

**Recommended Git milestone**: tag `v0.1.0-foundation`; branch protection on `main` enabled from this point forward.

---

## Stage 2 — EnergyPlus Bridge

**Objective**: a real EnergyPlus simulation running under external Python control, with sensors readable and actuators writable, validated in isolation before anything else depends on it.

**Prerequisites**: Stage 1 (config).

**Components to build**: `bridge/` (lifecycle, callback registration, handle resolution per `07_EnergyPlus_Design.md` §1–3); `comfort/` (PMV/PPD, since the Bridge calls it every timestep per `05_Runtime_Execution.md` §3, independent of any agent).

**Expected outputs**: a short design-day run against a real `.idf`/`.epw` pair produces a full-resolution, per-timestep sensor stream (written to a local file/stdout stub — Storage does not exist yet) and accepts a scripted actuator override that is observably in effect on the next read.

**Validation criteria**: FR-1, FR-2, FR-3 demonstrated; handle resolution correctly gated on `api_data_fully_ready` (`07_EnergyPlus_Design.md` §1); warmup and design-day environments correctly excluded from any "would this be a decision cycle" check, even though no agent exists yet to receive it (`01_Requirements.md` Edge Cases 1–2).

**Estimated complexity**: High — this is the stage with the most version- and model-specific uncertainty in the whole project.

**Potential implementation risks**: R-08 (API/version drift), R-11 (config-actuator/`.idf` mismatch).

**Recommended Git milestone**: tag `v0.2.0-bridge`.

**Parallelizable side-track**: `idf_tools/` (offline `eppy`-based ECM sweep generation, FR-11) depends only on Stage 1, not on the Bridge (`07_EnergyPlus_Design.md` §4 establishes these as two independent mechanisms) — a second engineer can build this alongside Stage 2 rather than waiting.

---

## Stage 3 — Storage

**Objective**: a durable, queryable record of everything the Bridge produces, with the specific async/backpressure behavior the architecture requires.

**Prerequisites**: Stage 1 (config: backend choice and path).

**Components to build**: `storage/` (schema per `11_Database_Design.md` §6; async write buffer with the documented drop-priority backpressure policy per `04_Dataflow.md` §3).

**Expected outputs**: the Bridge's sensor stream (Stage 2) now lands in DuckDB/SQLite tables instead of a stub sink; a fault-injected slow-write test shows the documented "drop telemetry before decision/incident records" behavior.

**Validation criteria**: RR-5 partially demonstrated (a restart does not duplicate rows); NFR-4's structured-log/correlation-ID threading is in place, using a placeholder `cycle_id` at this stage since the Agent (which mints real `cycle_id`s) does not exist yet — recorded here as an implementation note, not a Project Bible contradiction.

**Estimated complexity**: Medium.

**Potential implementation risks**: R-12 (backpressure drops more than intended under sustained load).

**Recommended Git milestone**: tag `v0.3.0-storage`.

**Parallelizable side-track**: once Storage exists, a full baseline (`run_mode: baseline`) simulation — Bridge + Storage only, no LLM, no MCP — can be run end-to-end here. This satisfies FR-9's "baseline" half well before the agent half exists, and should be produced now rather than deferred to Stage 6, since it needs nothing from Stages 4–5.

---

## Stage 4 — MCP Server

**Objective**: all ten tools from `09_MCP_Architecture.md` implemented and contract-tested against a real MCP client — with no LLM in the loop yet. Tools are exercised directly by test harnesses.

**Prerequisites**: Stage 2 (Bridge, for `get_zone_state`/`apply_setpoints`), Stage 3 (Storage, for `get_history`/`log_decision`/`raise_incident`).

**Components to build**: `mcp_server/` (server + tool registration, stdio transport per ADR-003); `optimizer/` (`propose_setpoints`'s deterministic solver, `06_Control_System.md` §2–3); `validator/` (`validate_action`'s bound-checking logic, `06_Control_System.md` §4).

**Expected outputs**: every tool in `09_MCP_Architecture.md` §2 callable and matching its declared schema, errors, and timeout exactly; the validator's property-based test suite (`13_Testing.md` §2) passing with zero false "pass" results across a large randomized input set.

**Validation criteria**: FR-6, SR-1, SR-2 demonstrated directly by the validator's property tests; the tool catalog contains exactly ten tools, no more (SR-3, ADR-011) — enforced as a CI check, not just a code review note.

**Estimated complexity**: Medium-High.

**Potential implementation risks**: R-01 (validator gap) is most directly mitigated by the investment made in this stage.

**Recommended Git milestone**: tag `v0.4.0-mcp-tools`.

---

## Stage 5 — LLM Agent

**Objective**: the full closed loop — a real LLM, a real ReAct-style loop, real tool calls — wired into the Bridge's decision-cycle hook for the first time.

**Prerequisites**: Stage 4 (MCP tools), plus a reachable LLM inference endpoint meeting ADR-004's requirements (native or grammar-constrained tool calling).

**Components to build**: `agent/` (orchestrator loop, two-tier memory per `08_LLM_and_Agent_System.md` §3, LLM client with constrained-decoding configuration per ADR-008); `monitoring/` (health/incident surface, needed from this stage on since this is where incidents start being generated).

**Expected outputs**: a full representative-day run under agent control, with genuine tool-calling traces recorded in `decision_logs`.

**Validation criteria**: FR-4, FR-5, FR-7, FR-8, FR-12, FR-13; acceptance criteria A1 and A3 become measurable for the first time; the fault-injection tests targeting failure conditions 1–4 and 8 (`01_Requirements.md` §10) are exercised against this stage specifically.

**Estimated complexity**: High — this stage carries most of the project's remaining integration risk (R-03, R-05, R-06, R-07, R-09 are all live from here on).

**Recommended Git milestone**: tag `v0.5.0-agent-loop`.

---

## Stage 6 — Analytics + Dashboard

**Objective**: turn accumulated Storage data into the specific, required comparison numbers.

**Prerequisites**: Stage 3 (Storage schema); a completed baseline run (available since Stage 3) and a completed agent run (available since Stage 5) to actually compare.

**Components to build**: `analytics/` (aggregation and `compare_runs` per `12_API_Design.md` §2); `dashboard/` (read-only rendering per `03_Component_Design.md` §8).

**Expected outputs**: `compare_runs` produces real numbers for a real (baseline, agent) run pair; the dashboard renders them within the PR-4 time budget.

**Validation criteria**: FR-9, FR-10, PR-4; acceptance criterion A2 becomes measurable.

**Estimated complexity**: Low-Medium.

**Recommended Git milestone**: tag `v0.6.0-dashboard`.

---

## Stage 7 — Full-System Testing

**Objective**: the cross-cutting fault-injection, stress, recovery, and regression suites (`13_Testing.md` §5–9) run against the fully assembled system. (Unit and integration tests for each component were built alongside Stages 2–6, not deferred to here.)

**Prerequisites**: Stages 2–6 complete.

**Components to build**: `tests/fault_injection/`, `tests/stress/`, `tests/recovery/`, `tests/regression/` suites.

**Expected outputs**: every one of the ten failure conditions in `01_Requirements.md` §10 has a passing test with an *observed* graceful-degradation outcome, not an outcome merely asserted by code inspection.

**Validation criteria**: acceptance criteria A1 through A5 all demonstrable end to end in one place.

**Estimated complexity**: Medium — mostly assembling and executing what `13_Testing.md` already fully specified.

**Recommended Git milestone**: tag `v0.7.0-verified`.

---

## Stage 8 — Deployment & Demo Packaging

**Objective**: containerize the system, produce the actual representative-day and full-annual-baseline runs for the demo, and assemble the remaining brief deliverables.

**Prerequisites**: Stage 7.

**Components to build**: per-component Dockerfiles (ADR-011's process isolation, made concrete); `scripts/` run orchestration; demo recording; presentation assembly.

**Expected outputs**: all Project Deliverables from the original brief — source code (done by Stage 7), `.idf` files (baseline + ECM variants, done by Stage 2's side-track), dashboard (Stage 6), this documentation, a demo video, and a presentation.

**Validation criteria**: every brief deliverable checked off; demo video captures the six specific beats the brief names (live data transfer, reasoning, action generation, dynamic update, end-to-end operation).

**Estimated complexity**: Low-Medium, with one significant exception (R-09).

**Potential implementation risks**: R-09 (demo-day hardware availability) — this is the stage where that risk actually materializes if it's going to.

**Recommended Git milestone**: tag `v1.0.0-poc`.

---

## Dependency summary (see `IMPLEMENTATION_DEPENDENCY_GRAPH.md` for the full diagram)

```
Stage 1 (Foundation)
   ├──> Stage 2 (Bridge) ──> Stage 4 (MCP Server) ──> Stage 5 (Agent) ──┐
   │         └── idf_tools (parallel, FR-11)                            ├──> Stage 6 (Analytics/Dashboard) ──> Stage 7 (Testing) ──> Stage 8 (Deployment)
   └──> Stage 3 (Storage) ──> Stage 4 (MCP Server)                      │
             └── baseline run (parallel, available from here) ──────────┘
```

## Final review checklist for this document

- [x] No stage lists a component from a later stage as a prerequisite.
- [x] Every component named in `03_Component_Design.md` appears in exactly one stage's "components to build."
- [x] Every risk in `16_Risk_Register.md` that is relevant to build order is attached to the stage where it first becomes live.
- [x] Parallelization opportunities (idf_tools, baseline run) are called out explicitly rather than left implicit, since a dependency-aware roadmap should show slack, not just the critical path.
