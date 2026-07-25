# DEVELOPMENT_SEQUENCE.md

Six weeks, sized for a small team (2–3 engineers) working from the frozen Project Bible — the upper end of the "2–6 weeks" PoC timeline `00_Project_Overview.md` assumed. A single-engineer or more compressed effort should still follow this same stage order (`IMPLEMENTATION_ROADMAP.md`'s dependency graph doesn't change), just with wider week boundaries; the parallel tracks called out below (idf_tools, baseline run) are exactly where an additional engineer shortens the calendar, not where the technical dependency order changes.

---

## Week 1 — Foundation + Bridge (start)

**Objectives**: Stage 1 complete; Stage 2 underway. Get a real EnergyPlus process running under external Python control before touching anything AI-related.

**Deliverables**: validated config schema and loader; CI green on both target OSes; a short design-day run producing a full-resolution sensor stream from a real `.idf`/`.epw` pair.

**Expected demo** (internal, end of week): a terminal run showing zone temperature and PMV printed every timestep for a 1–2 day simulation, with a scripted actuator override visibly taking effect.

**Risk areas**: R-08 (EnergyPlus API/version specifics) — this is the week most likely to reveal a `.idf`-specific surprise (an actuator that doesn't exist the way the config assumed, per R-11). Budget slack here rather than in later weeks; a slip in Week 1 is cheaper to absorb than a slip in Week 4.

---

## Week 2 — Bridge (finish) + Storage + idf_tools (parallel)

**Objectives**: Stage 2 complete and validated end to end; Stage 3 complete; the `idf_tools` ECM-sweep side-track built by a second engineer in parallel, since it has zero dependency on Bridge/Storage.

**Deliverables**: sensor and decision telemetry landing durably in DuckDB/SQLite; backpressure behavior verified under a simulated slow write; a completed full-annual baseline run (Bridge + Storage only, no agent) archived; at least one generated ECM `.idf` variant validated and run independently.

**Expected demo**: a completed baseline run's data queryable directly from the database (total kWh, PMV distribution) with no agent code involved at all — this is genuinely useful progress visible without waiting for Stage 5.

**Risk areas**: R-12 (backpressure dropping more than intended) — worth deliberately fault-injecting this week while the storage layer is fresh in mind, rather than discovering it during Stage 7.

---

## Week 3 — MCP Server

**Objectives**: all ten tools built, schema-validated, and contract-tested; the deterministic core (`comfort/`, `optimizer/`, `validator/`) complete and property-tested — still with no LLM in the loop.

**Deliverables**: a passing contract-test suite for every tool in `09_MCP_Architecture.md`; the validator's property-based fuzz suite passing with zero false "pass" results.

**Expected demo**: a test harness (not an LLM) calling each MCP tool directly over stdio and getting back exactly the documented schema — including deliberately triggering every documented `isError` case and confirming the response shape.

**Risk areas**: R-01 (validator gap) is the single highest-stakes risk in the entire project and this is the week it's addressed head-on. Do not compress this week's testing effort to make up time lost in Week 1 — the schedule should protect this week's validator fuzz-testing budget specifically.

---

## Week 4 — LLM Agent

**Objectives**: the full closed loop, for the first time — real LLM, real ReAct loop, real tool calls, wired into the Bridge.

**Deliverables**: a complete representative-day run under genuine agent control, with tool-calling traces in the decision log; fault-injection tests for LLM-unreachable, malformed-call, and out-of-bound-action conditions passing with observed graceful degradation.

**Expected demo**: the first real end-to-end run — this is the week's most important milestone and should be recorded even in rough form, since it's the closest rehearsal available for the eventual demo video.

**Risk areas**: this week concentrates the largest number of live risks (R-03 LLM server stability, R-05 context growth, R-06 comfort-vs-energy trade-off tuning, R-07 non-determinism, R-09 hardware availability). If the schedule is going to slip anywhere, it will be here — Week 5's scope (Analytics/Dashboard) is the easiest to compress if Week 4 needs the extra time, since Analytics can already run against Week 2's baseline-only data in the meantime.

---

## Week 5 — Analytics + Dashboard + Testing (start)

**Objectives**: Stage 6 complete; Stage 7's fault-injection and stress suites underway, run against the now-complete system.

**Deliverables**: `compare_runs` producing real baseline-vs-agent numbers; dashboard rendering them within budget; the remaining failure conditions (database write failure, concurrent apply, process restart) fault-injected and passing.

**Expected demo**: the actual comparison dashboard, populated with the actual runs produced in Weeks 2 and 4 — this is the artifact the brief's "Quantitative Savings Dashboard" deliverable maps directly onto.

**Risk areas**: R-04 (if representative-day sampling wasn't already locked in during earlier weeks' config, this is where an over-ambitious full-annual AI-driven run attempt would surface as a schedule risk — it shouldn't, since PR-3/ADR-009 already ruled this out, but it's worth confirming the actual run configuration used matches the documented decision).

---

## Week 6 — Testing (finish) + Deployment + Demo

**Objectives**: Stage 7 fully complete (all ten failure conditions, stress, recovery, regression); Stage 8 complete (containerization, final runs archived, demo video, presentation).

**Deliverables**: a consolidated test report showing acceptance criteria A1–A5 all satisfied; Dockerfiles for each major component; the final representative-day and full-annual-baseline runs; the demo video; the presentation.

**Expected demo**: the actual deliverable — a ≤3-minute recording covering live data transfer, AI reasoning, control-action generation, dynamic parameter updates, and end-to-end operation, per the brief's explicit requirements.

**Risk areas**: R-09 (demo-day hardware) — the fallback plan (smaller/quantized CPU-runnable model, or a pre-recorded run as backup) should be rehearsed this week, not improvised on the day.

---

## What this sequence deliberately does not do

It does not compress testing into a single end-of-project week beyond the cross-cutting suites that genuinely require the whole system assembled (Stage 7) — unit and property tests for `validator/`, `comfort/`, and `optimizer/` are built in Weeks 2–3, alongside the modules they test, per `MODULE_BREAKDOWN.md`'s per-module test requirements. A schedule that deferred all testing to Week 6 would leave R-01 (the validator) under-tested for five weeks before anyone looked closely at it — exactly the failure mode this sequence is structured to avoid.
