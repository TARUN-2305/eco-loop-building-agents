# CODE_QUALITY_GUIDE.md

These rules are specific to this project's architecture, not generic style preferences — each is traceable to a Project Bible decision. Where a rule is genuinely just team convention rather than architecturally required, it's marked **(convention)** rather than implied to be load-bearing.

## Naming conventions

- Module names match `MODULE_BREAKDOWN.md` exactly (`bridge`, `comfort`, `optimizer`, `validator`, `agent`, `mcp_server`, `storage`, `analytics`, `dashboard`, `idf_tools`, `monitoring`, `shared`, `config`) — a renamed module without a corresponding update to the Project Bible and this implementation package is a documentation-drift bug, not a harmless refactor.
- Every identifier that appears as a field name in `09_MCP_Architecture.md`'s tool schemas (`cycle_id`, `air_temp_c`, `predicted_kwh_horizon`, etc.) is used verbatim in code — no renaming a schema field to a "nicer" Python name partway through the stack. The schema is the frozen contract; code names follow it, not the other way around.
- `cycle_id` is always the name for the decision-cycle correlation ID, everywhere in the codebase — never `decision_id`, `turn_id`, or a local synonym.
- Files implementing one MCP tool are named `<tool_name>.py` inside `mcp_server/tools/` (e.g., `propose_setpoints.py`) — a one-to-one, unambiguous mapping between tool name and file.

## Typing

- Every public function signature across every module in `MODULE_BREAKDOWN.md` is fully type-annotated — this is not a style preference here, it's what makes `TRACEABILITY_MATRIX.md`'s "independently testable with the others mocked" (NFR-1) practical: a mock is only trustworthy if the real interface's types are explicit.
- Shared record types (`SensorSnapshot`, `CandidateAction`, `ValidationResult`, `DecisionLog`, `Incident`, `RunSummary`) are defined once, in `shared/types.py`, as typed dataclasses or pydantic models — never redefined or duck-typed differently in a second module.
- MCP tool inputs/outputs are validated against their JSON Schema at the server boundary (`mcp_server/`) in addition to being typed in Python — the two are complementary: Python typing catches internal mistakes at development time, schema validation catches a malformed call from the LLM at runtime, which Python types alone cannot do.

## Error handling

- A tool execution error (something the domain logic legitimately rejects — an infeasible optimization, an out-of-bound validation) is returned as a normal, typed result (`isError: true` per `09_MCP_Architecture.md`), never raised as a Python exception that propagates out of the tool boundary. A genuinely unexpected internal fault (a bug) is the only thing that should raise past the MCP server boundary, and even then, the server catches it and converts it to a protocol-level error rather than crashing the process (RR-1).
- `bridge/` never lets an exception from `pyenergyplus` propagate silently — every callback registered with the Runtime API wraps its body so a Python-side exception is logged with full context and triggers the documented fallback path, rather than becoming an unhandled exception inside an EnergyPlus callback (which could leave the simulation in an undefined state — the opposite of SR-4's "prefer the safest known state").
- Retries follow `04_Dataflow.md` §4 exactly: idempotent read-only tools may be retried by the caller; `apply_setpoints` is never retried by generic retry middleware — if a retry-wrapping decorator or library is used elsewhere in the codebase **(convention: prefer explicit retry logic over a blanket decorator for exactly this reason)**, `apply_setpoints`'s call site must not be wrapped by it.

## Logging

- All logging goes through `shared/logging.py`'s wrapper, which enforces structured JSON output and `cycle_id` inclusion wherever a `cycle_id` is in scope (NFR-4) — no module calls Python's `logging` module directly with ad hoc string formatting.
- Log levels: `DEBUG` for per-timestep telemetry detail; `INFO` for per-cycle decisions; `WARNING` for recoverable faults (retried tool calls, recoverable EnergyPlus severities); `ERROR`/`INCIDENT` for anything that triggers a fallback or degraded mode — `monitoring/`'s health signal is derived from `INCIDENT`-level log volume, so this level must be used consistently, not loosely.
- Logging from inside a Bridge callback is non-blocking (buffered handler) — a synchronous, slow log sink must never add latency to the EnergyPlus callback path (`02_Architecture.md` §1's synchronous-core principle applies to logging too, not just to Storage writes).

## Configuration

- No comfort band, cadence, actuator bound, or objective weight is ever hard-coded in a module — every such value is read from `Config`, loaded once at process start (NFR-3). A grep for a bare numeric literal that looks like a temperature or a percentage in `bridge/`, `optimizer/`, or `validator/` is a code-review flag.
- Config is immutable after load (`ARCHITECTURAL_GUARDRAILS.md`) — no module mutates its own copy of `Config` at runtime; a run that needs different parameters is a new config file and a new process, not a live mutation.

## Documentation

- Every module's top-of-file docstring states which Project Bible document(s) it implements (e.g., `validator/bounds.py`'s docstring references `06_Control_System.md` §4 and `09_MCP_Architecture.md` §2.6) — this is what keeps `TRACEABILITY_MATRIX.md` verifiable against the actual code, not just against intentions.
- Public function docstrings state pre/post-conditions where they matter for safety (e.g., `validator.validate()`'s docstring states it is pure, total, and never raises).

## Testing requirements

- Every module in `MODULE_BREAKDOWN.md` ships with the specific unit and integration tests that document names for it — a module without its required test coverage is not considered complete, regardless of whether it "works" in manual testing.
- `validator/` and `optimizer/` unit tests must include property-based/fuzz cases, not only example-based cases — a handful of hand-picked example inputs is not sufficient evidence for the single most safety-critical module in the codebase (`13_Testing.md` §2, §8).
- No test suite asserts "the LLM produced a good answer" as a pass/fail condition — LLM output quality is evaluated qualitatively during development, never gated on by an automated test that would be non-deterministic and untrustworthy (`13_Testing.md` §8's "test the guardrail, not the model" principle).

## Performance requirements

- Any code on the decision-cycle critical path (`bridge/`, `agent/orchestrator.py`, the deterministic MCP tools) is profiled against the budgets in `15_Performance.md` §1 before being considered complete, not only functionally tested.
- Logging, Storage writes, and Dashboard rendering are never added to the synchronous critical path — if a change to any of these three modules would add blocking latency to a decision cycle, that change is a design defect, not a performance detail to optimize later.

## Security requirements

- No new MCP tool is added without updating `09_MCP_Architecture.md` and `ARCHITECTURAL_GUARDRAILS.md` first — the tool catalog being fixed at ten is enforced by CI (`IMPLEMENTATION_CHECKLIST.md`), and a code change that adds an eleventh tool without a corresponding, deliberate Project Bible amendment is a guardrail violation, not a feature.
- No module outside `bridge/` and `mcp_server/tools/apply_setpoints.py` calls anything that writes to an EnergyPlus actuator — this is enforced by code review and, where practical, by an import-linter rule in CI, not left to convention alone.
- No tool, anywhere, executes a shell command, writes an arbitrary file, or evaluates dynamic code from LLM-supplied input.

## Formatting

- **(convention)** One formatter (e.g., `black`) and one linter (e.g., `ruff`) applied uniformly, enforced in CI, so code review time is spent on substance (does this respect the architecture) rather than style debates.
- **(convention)** Line length, import ordering, and docstring style follow whatever the team's chosen formatter/linter defaults to — this project does not prescribe a specific style beyond "one tool enforces it consistently."

## Folder conventions

- Every module directory has an `__init__.py` exposing exactly the public interface named in `MODULE_BREAKDOWN.md` — internal helper functions are not importable from outside the module's own directory, which is what makes the dependency graph in `IMPLEMENTATION_DEPENDENCY_GRAPH.md` an enforceable fact about the codebase rather than only a description of intent.
- Test directories mirror `src/` structure for `tests/unit/` and `tests/integration/`, per `REPOSITORY_STRUCTURE.md`; scenario-based suites (`fault_injection/`, `stress/`, `recovery/`, `regression/`) are organized by scenario, not by module.
