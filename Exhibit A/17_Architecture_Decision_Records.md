# 17 — Architecture Decision Records

Each ADR follows: Context → Alternatives Considered → Decision → Consequences (including accepted downsides, not just benefits). These are the load-bearing decisions referenced throughout this Project Bible; each entry below is the canonical record for a reasoning chain summarized elsewhere.

---

## ADR-001: Python as the implementation language

**Context**: The brief states a Python preference; the simulation-coupling and tool-protocol ecosystems both need to be evaluated on their own merits regardless.

**Alternatives considered**: C++ (EnergyPlus's own implementation language, offering direct access with no binding overhead), Julia (strong in scientific/optimization computing, growing simulation ecosystem), Java/JVM (BCVTB's own ecosystem language).

**Decision**: Python.

**Consequences**: Direct, first-party access to both `pyenergyplus` (the Runtime API) and `eppy` (offline `.idf` editing), plus the deepest current ecosystem for MCP SDKs, LLM-serving clients, and data/analytics tooling (DuckDB, pandas-adjacent tooling). Accepted downside: Python's own performance ceiling is irrelevant here (the bottleneck is LLM inference, not Python execution, per `15_Performance.md` §1), so this cost is real in general but not binding for this specific system.

---

## ADR-002: EnergyPlus Python Runtime API over EMS/Erl, Python Plugins, or BCVTB/FMU

**Context**: Full reasoning in `02_Architecture.md` §3.1 and `07_EnergyPlus_Design.md`.

**Alternatives considered**: EMS/Erl (in-`.idf` scripting), Python Plugin system (`.idf`-declared plugin scripts), BCVTB (Ptolemy-II-based co-simulation middleware), EnergyPlusToFMU/FMU export.

**Decision**: External Python script using the Runtime API (`pyenergyplus.api.EnergyPlusAPI`), driven by callbacks, calling out to the MCP server and LLM from within those callbacks.

**Consequences**: Full general-purpose-language capability (HTTP calls, MCP client, DB writes) inside the control loop, and clean separation from the `.idf` itself (no plugin declarations coupling code to one specific model). Accepted downside: this couples the project to whatever version-specific handle/actuator behavior the installed EnergyPlus release exposes, mitigated by explicit version pinning and startup-time validation (R-08, `16_Risk_Register.md`).

---

## ADR-003: MCP (stdio transport) over a custom REST API or in-process function-calling

**Context**: Full reasoning in `02_Architecture.md` §3.2 and `09_MCP_Architecture.md` §1.

**Alternatives considered**: native LLM-SDK function-calling with in-process Python functions; a hand-rolled REST/OpenAPI tool server.

**Decision**: MCP server, stdio transport for the PoC, with Streamable HTTP named as the documented upgrade path if the tool server is ever split onto a separate host.

**Consequences**: A real process boundary between "what the agent can do" and "how it's implemented" (a security property, not just an abstraction), a standardized error model (protocol vs. tool-execution errors) this project's self-correction logic directly depends on, and portability to any MCP-compatible host later. Accepted downside: an extra process and IPC layer versus a bare in-process function call, which is a negligible cost at this system's scale and latency budget.

---

## ADR-004: Self-hosted open-weight LLM, requirements-based model selection (not one named model hard-coded)

**Context**: Full reasoning in `08_LLM_and_Agent_System.md` §5; the brief mandates an open-source/self-hosted model.

**Alternatives considered**: hard-coding one specific current model name into the architecture.

**Decision**: specify the *requirements* a model+serving-stack pair must meet (native or grammar-constrained tool calling; sufficient context for the rolling-window + tool-schema prompt; latency within `15_Performance.md`'s budget on available hardware) and select the actual model against those requirements at implementation time.

**Consequences**: The architecture survives the open-weight model landscape moving (which it does, quickly — several qualifying model families exist at time of writing and that list will look different within a year). Accepted downside: this defers a concrete decision the brief's own example list (Llama 3, Mistral, Qwen) seems to invite making up front; this is treated as a benefit, not a gap, given how fast this space moves.

---

## ADR-005: Hybrid control — LLM supervisor + deterministic optimizer + deterministic validator, over pure MPC, pure RL, pure end-to-end LLM control, or pure Bayesian optimization

**Context**: Full reasoning, with cited evidence, in `06_Control_System.md`.

**Alternatives considered**: PID, rule-based-only, pure MPC, pure RL, pure end-to-end LLM control, pure Bayesian optimization, treating the EnergyPlus model as a full production digital twin.

**Decision**: LLM reasons about *when* and *what to weight*; a small deterministic optimizer computes the actual candidate setpoints; a separate deterministic validator gates every commit.

**Consequences**: Satisfies the brief's explicit agentic-tool-use requirement without asking an LLM to be a numeric optimizer, and produces an auditable, property-testable safety core independent of LLM behavior. Accepted downside: does not capture MPC's full receding-horizon optimality or RL's potential to discover non-obvious policies through learning — both are named as legitimate future-work directions (§1.3/§1.4 of `06_Control_System.md`), not dismissed, just not built in this phase.

---

## ADR-006: DuckDB (or SQLite) embedded storage for the PoC, TimescaleDB as the named production migration target

**Context**: Full reasoning in `11_Database_Design.md`.

**Alternatives considered**: SQLite alone, Redis, InfluxDB, plain PostgreSQL, JSON files, Parquet-only.

**Decision**: DuckDB (SQLite as an equally acceptable fallback) embedded for the PoC; Parquet for run archival; TimescaleDB named as the concrete production-scale migration target ahead of InfluxDB, on the strength of full relational-join support against building/zone metadata this project's schema depends on.

**Consequences**: Zero additional server processes for the PoC; a real, specific (not hand-wavy) path to a production-scale store if this system's scope grows. Accepted downside: DuckDB/SQLite's single-node nature would need to change for genuine multi-building fleet scale — explicitly out of scope for this phase (`00_Project_Overview.md` §3.2).

---

## ADR-007: Synchronous, in-callback decision invocation over an async message-queue architecture for the core control loop

**Context**: Full reasoning in `02_Architecture.md` §1, resting on the documented fact that EnergyPlus's Runtime API callbacks block EnergyPlus's own execution until the Python callback returns.

**Alternatives considered**: a fully async, queue-mediated architecture decoupling the Bridge's timestep callback from the Agent Orchestrator's reasoning loop.

**Decision**: the decision-cycle path is a direct, synchronous, bounded-timeout call from the Bridge into the Agent Orchestrator; only the logging/telemetry path is async.

**Consequences**: Avoids a whole category of complexity (queue backpressure, out-of-order delivery, "what if the queue is still processing timestep N-3's decision when timestep N arrives") that a system with a genuine hard real-time deadline would need but this one does not, because EnergyPlus itself is not real-time. Accepted downside: wall-clock time really is added per decision cycle (there's no free lunch); this is bounded and budgeted explicitly in `15_Performance.md` rather than hidden by async decoupling.

---

## ADR-008: Decoder-level constrained/structured output for tool calls, with a mandatory separate semantic validator (not a substitute for one)

**Context**: Current practitioner guidance and this project's own reliability requirements (`08_LLM_and_Agent_System.md` §5, `06_Control_System.md` §1.5).

**Alternatives considered**: free-form JSON generation with regex/best-effort parsing and repair; relying on prompting alone ("please always respond with valid JSON") without decoder-level enforcement.

**Decision**: enable grammar/JSON-schema-constrained decoding for tool calls where the serving stack supports it, and treat this as solving *syntax* reliability only — `validate_action`'s semantic check remains mandatory and independent regardless.

**Consequences**: Eliminates an entire class of malformed-call failures cheaply, at essentially the cost of a serving-stack configuration flag. Accepted downside: none of significance — the risk here is misinterpreting this as sufficient on its own, which this ADR (and `06_Control_System.md` §1.5) explicitly guards against.

---

## ADR-009: Representative-day sampling for the AI-driven demo run, full-annual reserved for the baseline-only comparison

**Context**: `01_Requirements.md` PR-3; `07_EnergyPlus_Design.md` §7; `16_Risk_Register.md` R-04.

**Alternatives considered**: every-timestep, full-annual AI-driven run.

**Decision**: run the baseline at full annual fidelity (cheap — no LLM in the loop); run the AI-driven comparison over a small set of representative days/weeks (shoulder season, peak heating, peak cooling) at full decision cadence.

**Consequences**: Keeps the PoC's wall-clock cost tractable without misrepresenting the comparison (the same representative period is used for both sides of the baseline-vs-agent comparison, so the methodology stays apples-to-apples). Accepted downside: the reported %-energy-reduction is a representative-period estimate, not a certified full-year figure — stated plainly in the Dashboard/report rather than implied to be more than it is.

---

## ADR-010: Deterministic, analytical PMV/PPD (Fanger/ISO 7730) over a learned comfort model

**Context**: `10_Machine_Learning.md` §6.

**Alternatives considered**: a learned/personalized comfort model.

**Decision**: use the standard analytical formula, computed as a pure deterministic tool (`compute_pmv`), for all comfort scoring in this system.

**Consequences**: Auditable, zero-training-data, standards-grounded comfort metric with known applicability bounds. Accepted downside: does not capture individual occupant preference variation — named explicitly as future work, not attempted here, because there is no real-occupant feedback data in a pure-simulation PoC to learn from anyway.

---

## ADR-011: Container-based process isolation, no shell/file/code-execution tool exposed to the agent

**Context**: `14_Security.md` §5.

**Alternatives considered**: a more flexible general-purpose "run a command" or "edit a file" tool, for agent convenience/flexibility.

**Decision**: fixed, narrow, ten-tool MCP surface only (`09_MCP_Architecture.md`); each major component (EnergyPlus, LLM server, MCP server) run as a separate, minimally-privileged, containerized process.

**Consequences**: Removes an entire, common class of agentic-AI-demo security shortcut before it's ever tempting to add "just for debugging." Accepted downside: slightly less flexibility for the agent to self-correct in truly novel ways outside the anticipated tool set — accepted deliberately, because that flexibility is exactly the unbounded capability this project's safety case depends on not existing.

---

## ADR-012: Markdown as the documentation format for this Project Bible

**Context**: The brief specifies Markdown documents explicitly.

**Alternatives considered**: none seriously — this one is close to a non-decision, included for completeness since the instruction was to record every important choice.

**Decision**: plain Markdown, one file per document, with Mermaid diagrams in fenced code blocks for every sequence/state/dependency diagram this Project Bible needed.

**Consequences**: Version-control-friendly (diffable in git, unlike a binary document format), renders diagrams-as-code rather than as unmaintainable pasted images, and matches the brief's own explicit format request. No meaningful accepted downside for this project's context.
