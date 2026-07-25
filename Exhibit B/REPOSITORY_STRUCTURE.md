# REPOSITORY_STRUCTURE.md

```
eco-loop-building-agents/
├── src/
│   ├── shared/
│   ├── config/
│   ├── bridge/
│   ├── comfort/
│   ├── optimizer/
│   ├── validator/
│   ├── agent/
│   ├── mcp_server/
│   │   └── tools/
│   ├── storage/
│   ├── analytics/
│   ├── dashboard/
│   ├── idf_tools/
│   └── monitoring/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── simulation/
│   ├── fault_injection/
│   ├── stress/
│   ├── recovery/
│   └── regression/
├── configs/
│   ├── baseline.yaml
│   └── agent.yaml
├── data/
│   ├── idf/
│   │   ├── baseline.idf
│   │   └── ecm_variants/
│   └── epw/
├── docs/
│   ├── project_bible/
│   └── implementation/
├── scripts/
├── .github/
│   └── workflows/
├── pyproject.toml (or requirements.txt + setup.cfg)
└── README.md
```

## Why each directory exists

### `src/` — every module named in `MODULE_BREAKDOWN.md`, one top-level package per component

One directory per component in `03_Component_Design.md`, matching `MODULE_BREAKDOWN.md`'s module list exactly, so there is no ambiguity about where a given piece of logic lives. The directory boundary **is** the enforcement mechanism for several `ARCHITECTURAL_GUARDRAILS.md` rules — e.g., "Bridge is the only EnergyPlus interface" is checkable by grepping for `pyenergyplus` imports outside `src/bridge/`, and "no component bypasses `validate_action`" is checkable by confirming `set_actuator_value`-equivalent calls only originate inside `src/bridge/` and `src/mcp_server/tools/apply_setpoints.py`.

- **`shared/`**: exists so `config/`, `bridge/`, `agent/`, `mcp_server/`, and `storage/` all agree on one definition of `SensorSnapshot`, `DecisionLog`, etc. Without this directory, type drift between modules would be a near-certainty (`MODULE_BREAKDOWN.md`).
- **`config/`**: isolated because it is the one module every other module reads but that itself reads nothing else at runtime (only, narrowly, `bridge/` at startup for actuator validation) — keeping it separate makes that asymmetry visible in the file tree, not just in prose.
- **`bridge/`**: isolated specifically to make "Bridge is the only EnergyPlus interface" trivially auditable — if `pyenergyplus` is imported anywhere outside this directory, that is a guardrail violation by definition, not a judgment call.
- **`comfort/`, `optimizer/`, `validator/`**: three separate directories, not one "control" directory, because each has a **different, deliberately distinct testing regime** (`MODULE_BREAKDOWN.md`): `comfort/` gets golden-value tests, `optimizer/` gets behavioral tests, `validator/` gets exhaustive property-based fuzzing. Separate directories keep each module's test suite scoped to exactly what it needs without one bloated "control" test directory conflating three different testing philosophies.
- **`agent/`**: isolated so it's the one place LLM-specific code lives — this makes "no component bypasses `validate_action`" and "LLM never writes actuators directly" auditable the same way `bridge/`'s isolation makes the EnergyPlus rule auditable: search for actuator-writing calls outside `bridge/`+`mcp_server/tools/apply_setpoints.py`, and none should originate in `agent/`.
- **`mcp_server/tools/`**: one file per tool, deliberately thin (`MODULE_BREAKDOWN.md` notes these are schema-validating adapters, not where logic lives), so the tool catalog itself is trivially enumerable — "exactly ten tools" (SR-3) is answerable by `ls src/mcp_server/tools/`.
- **`storage/`, `analytics/`, `dashboard/`**: three separate directories reflecting the "Storage is async, Analytics reads it in batch, Dashboard is read-only" layering (`ARCHITECTURAL_GUARDRAILS.md`) — collapsing these into one directory would make the read/write asymmetry harder to see and easier to accidentally violate.
- **`idf_tools/`**: isolated specifically because `07_EnergyPlus_Design.md` §4 insists this is a *different mechanism* from the Bridge's runtime control — a separate top-level directory (not a subdirectory of `bridge/`) makes that distinction structural, not just documented.
- **`monitoring/`**: isolated because it is explicitly not the same thing as logging (`03_Component_Design.md` §11) — a separate directory prevents the two concerns from merging back together over time as the codebase grows.

### `tests/` — one directory per testing category from `13_Testing.md`, mirroring `src/` inside `unit/` and `integration/`

`tests/unit/` and `tests/integration/` each mirror `src/`'s package structure (e.g., `tests/unit/validator/test_bounds_property.py`) so a module's tests are easy to locate from its implementation and vice versa. `tests/simulation/`, `tests/fault_injection/`, `tests/stress/`, `tests/recovery/`, and `tests/regression/` are **not** mirrored per-module, because each of these categories inherently spans multiple modules at once (a fault-injection test exercises Bridge, MCP Server, and Agent together) — giving them their own top-level directories, organized by *scenario* rather than by *module*, matches how `13_Testing.md` itself organizes them.

### `configs/` — actual, runnable configuration files, distinct from `src/config/`'s schema code

`src/config/` is code (the schema and loader); `configs/` is data (the actual YAML files used for a given run, e.g., `baseline.yaml` for `run_mode: baseline` and `agent.yaml` for `run_mode: agent`). Keeping these separate follows the general principle (`CODE_QUALITY_GUIDE.md`) of not mixing code and its configuration data in the same directory tree, and makes it obvious at a glance which files a non-engineer (reviewing the demo setup) needs to touch versus which are implementation.

### `data/` — building models and weather files, the FR-11 ECM variants included

`data/idf/baseline.idf` is the one model this whole project revolves around; `data/idf/ecm_variants/` is exactly where `idf_tools/`'s output lands, keeping generated variants visibly separate from the hand-authored baseline. `data/epw/` holds the weather file(s) — kept out of `configs/` because weather data is a large, binary-ish, rarely-hand-edited asset, unlike the YAML configs which are small and frequently adjusted.

### `docs/` — this Project Bible and this implementation package, kept as first-class repository content

`docs/project_bible/` holds the 18 frozen architecture documents; `docs/implementation/` holds this ten-document implementation package. Both live in the repository itself (not in an external wiki) specifically because `01_Requirements.md` NFR-1/NFR-4 and this whole implementation package's philosophy treat the documentation as load-bearing, versioned artifacts that should move through git history alongside the code they describe — a docs change and the code change it motivated should be reviewable in the same pull request.

### `scripts/` — CLI entry points that orchestrate a run, distinct from the modules that implement one

`scripts/run_baseline.py`, `scripts/run_agent.py`, `scripts/run_ecm_sweep.py`, and any demo-recording helper live here rather than inside `src/` because they are orchestration (parse arguments, load config, call into `src/bridge/`'s `run()`), not reusable library code another module would import — keeping them out of `src/` keeps `src/`'s import graph (the thing `IMPLEMENTATION_DEPENDENCY_GRAPH.md` documents) free of command-line-parsing concerns.

### `.github/workflows/` — CI, referenced from Stage 1 of `IMPLEMENTATION_ROADMAP.md`

Standard location for the OS-matrix (NFR-2), lint, and test-suite-tier (unit/integration on every push; simulation/fault-injection/stress on a slower schedule) automation.

## What is deliberately absent from this structure

No `utils/` or `helpers/` catch-all directory: per `MODULE_BREAKDOWN.md`, every piece of shared logic has a specific, named home (`shared/` for types and logging, or the specific component it belongs to) — a generic dumping-ground directory is exactly the kind of structure that erodes the auditability this whole layout is designed to preserve. No `notebooks/`: exploratory analysis, if needed during development, is not part of the repository this Project Bible describes shipping.
