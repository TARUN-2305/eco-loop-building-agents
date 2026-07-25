# Architectural Security & Guardrails Audit

**System Name:** Eco-Loop Building Agents  
**Role:** Principal Verification & Validation Engineer  
**Date:** July 25, 2026  

---

## 1. Audit Summary: 23 Architectural Guardrails Verification

| Guardrail # | Description | Empirical Verification Evidence | Audit Result |
| :--- | :--- | :--- | :--- |
| **G-1** | `src/bridge/` is sole `pyenergyplus` importer | Ripgrep audit confirms zero imports of `pyenergyplus` outside `src/bridge/` | **COMPLIANT** |
| **G-2** | No out-of-band actuator writes | All writes pass through `HandleManager.commit_actuator()` | **COMPLIANT** |
| **G-3** | Offline IDF editing only | `src/idf_tools/` operates offline; no mid-run `.idf` hot-reload | **COMPLIANT** |
| **G-4** | `validate_action` mandatory before write | `apply_setpoints` re-validates server-side before write | **COMPLIANT** |
| **G-5** | `apply_setpoints` re-validates server-side | Server-side re-validation enforced in `execute_apply_setpoints()` | **COMPLIANT** |
| **G-6** | LLM does not perform setpoint arithmetic | Arithmetic performed deterministically by `propose_setpoints_solver` | **COMPLIANT** |
| **G-7** | LLM cannot write actuators directly | LLM has zero direct handle or C-API access; mediated by MCP tool | **COMPLIANT** |
| **G-8** | Deterministic PMV computation | `compute_pmv()` uses Fanger analytical formula | **COMPLIANT** |
| **G-9** | Hard-coded min/max bounds | Loaded from immutable config; enforced by validator gate | **COMPLIANT** |
| **G-10** | Fail-safe hold-last-known-good | Re-asserts last committed value on validator/LLM rejection | **COMPLIANT** |
| **G-11** | No shell, file-write, or exec tools exposed | `mcp_server/tools/` contains zero system/exec/file tools | **COMPLIANT** |
| **G-12** | Fixed 10-tool MCP catalog | `len(get_tool_catalog()) == 10` verified by test suite | **COMPLIANT** |
| **G-13** | Immutable operational config | `Config` dataclasses frozen post-load | **COMPLIANT** |
| **G-14** | Bounded history query access | `get_history` limits output (top 5 similar days) | **COMPLIANT** |
| **G-15** | Synchronous decision loop in callback | Decision cycle executes synchronously inside timestep callback | **COMPLIANT** |
| **G-16** | Asynchronous storage queue | Telemetry written via non-blocking background queue thread | **COMPLIANT** |
| **G-17** | Idempotency by `cycle_id` | Repeat writes with same `cycle_id` & value are no-ops | **COMPLIANT** |
| **G-18** | No blind retries on transport failure | Transport failures trigger fallback and degraded mode | **COMPLIANT** |
| **G-19** | Every tool call logged with `cycle_id` | `ToolTrace` records `cycle_id`, tool name, args, result | **COMPLIANT** |
| **G-20** | Immutable runtime configuration | Configuration cannot be mutated during simulation run | **COMPLIANT** |
| **G-21** | Read-only Dashboard | HTTP POST/PUT/DELETE return HTTP 405 Method Not Allowed | **COMPLIANT** |
| **G-22** | Simulation safety boundary | System operates against EnergyPlus simulation only | **COMPLIANT** |
| **G-23** | ADR-001 through ADR-012 preserved | Architectural decisions intact | **COMPLIANT** |

---

## 2. Conclusion
Zero architectural guardrail violations were detected. The security perimeter and control boundaries strictly conform to Exhibit A specifications.
