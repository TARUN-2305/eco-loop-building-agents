# 15 — Performance

This document directly answers two things the brief names explicitly as required deliverable content: "prompt latency management" and "a technical approach for handling lengthy simulation logs." Both get a concrete, specific answer here, not a general gesture at "we'll optimize as needed."

## 1. Where the latency actually goes

| Stage | Typical cost | Is it the bottleneck? |
|---|---|---|
| Sensor read (`api.exchange.get_variable_value` × N) | Low single-digit ms | No |
| `compute_pmv` | < 20 ms (pure arithmetic) | No |
| LLM reasoning turn(s), including tool round-trips | Low seconds to several seconds, dominated by token generation | **Yes — this is the critical path** |
| `propose_setpoints` (deterministic optimizer) | < 500 ms | No |
| `validate_action` | < 20 ms | No |
| Actuator commit | Low single-digit ms | No |
| Async log/telemetry write | Not on the critical path at all (fire-and-forget, `04_Dataflow.md` §3) | No |

The entire latency budget problem in this system reduces to one thing: **LLM token generation time**, multiplied by however many reasoning turns and tool round-trips a cycle takes. Everything else in the table is fast enough not to matter. This is why `01_Requirements.md` PR-1's 8-second-P95 budget is framed around the LLM call specifically.

## 2. Prompt latency management — the concrete mechanisms

1. **Static prefix caching.** The system prompt and the full tool-schema set do not change cycle to cycle; keeping them as a stable prefix and only appending new observation/turn content lets the serving stack (Ollama/vLLM/llama.cpp-class servers all support some form of prefix/KV-cache reuse) skip re-processing the unchanging portion of the prompt on every call. This is a real, well-understood optimization in local LLM serving, not a novel idea — the design obligation here is simply to *not* defeat it by, e.g., re-ordering or re-formatting the static portion between calls in a way that breaks the cache match.
2. **Bounded, small tool-call budget per cycle** (default 6): directly bounds worst-case cycle latency as `budget × per-call latency`, rather than leaving it open-ended.
3. **Small, sharply-defined tool catalog** (ten tools, `09_MCP_Architecture.md`): keeps the per-turn prompt (tool schemas included) as small as it can be while still being complete, which both reduces token count per call and — per `08_LLM_and_Agent_System.md` §5 — improves tool-selection reliability.
4. **A quantized, appropriately-sized model for the tight loop, with a heavier/slower model reserved for the once-a-day reflection step where the latency budget is loose** (`08_LLM_and_Agent_System.md` §3) — this is a deliberate two-tier latency budget, not one model doing everything at one fixed cost.
5. **Cycle-level timeout, not just call-level**: the whole cycle (including all tool round-trips) is wrapped in a timeout that triggers the fallback path if exceeded, so a single slow call can't silently blow the whole simulation's wall-clock budget — this is a reliability mechanism (`01_Requirements.md`, RR-1/RR-3) that is also, in effect, a hard performance guarantee.

## 3. The "lengthy simulation logs" problem — the concrete mechanism

The brief calls this out by name as something to solve, and the direct, specific answer is a **"pull, not push" pattern**, applied consistently everywhere raw telemetry could otherwise flood the LLM's context:

1. **Raw per-timestep telemetry never enters the LLM's prompt by default, ever** — the LLM sees only the current `SensorSnapshot` (one small structured object) plus Memory's rolling window and reflection summary, never a dump of recent history.
2. **Historical data is retrieved through the `get_history` tool, which returns bounded, pre-aggregated results** (`09_MCP_Architecture.md` §2.8) — a fixed set of query shapes (similar-conditions lookup, recent-incidents lookup, daily-summary lookup), never a free-form or unbounded query, and never raw rows.
3. **Memory compaction, not accumulation** — the rolling window holds only the last few cycles verbatim; older content is periodically folded into a single regenerated natural-language reflection summary (`08_LLM_and_Agent_System.md` §3) rather than being appended to an ever-growing transcript. This is the mechanism that keeps a multi-day run's prompt size roughly constant instead of growing linearly with run length.
4. **Any genuinely long text a component might need to hand the LLM (an EnergyPlus error/warning message, for instance) is summarized or truncated to its essential content before it reaches the prompt**, not passed through verbatim — the same principle as #1–2, applied to unstructured text specifically.

This four-part answer is deliberately concrete rather than a general "we'll manage context carefully" statement, because "handling lengthy simulation logs" was named as an explicit required deliverable, not a nice-to-have.

## 4. Caching (beyond prompt caching)

- `compute_pmv` results are trivially cacheable within a single timestep if called more than once (it's pure and cheap enough that this is a minor optimization, not a load-bearing one).
- `get_weather_forecast` results for the same simulated hour are cached for the duration of that hour rather than re-derived on every call within it.
- Tool calls are de-duplicated within a single cycle where the same call with the same arguments would otherwise be issued twice (a defensive measure against a redundant LLM tool call, not an expected common case).

## 5. Parallelism

- **Baseline and agent-driven runs, or multiple representative-day runs within a sweep, are embarrassingly parallel across separate OS processes** — EnergyPlus does not need to share any state across independent scenario runs, so scenario comparison should be parallelized at the process level (separate EnergyPlus states in separate processes), not via threads within one process, which sidesteps both Python's GIL and any EnergyPlus-side thread-safety concerns around running multiple states concurrently in one process.
- Within a single run, the core decision loop is intentionally **not** parallelized (`02_Architecture.md` §1) — there is exactly one thing happening at a time by design (EnergyPlus's callback blocks until the Bridge/Agent returns), and introducing parallelism into that path would only add complexity for a problem (throughput of one simulation) that process-level parallelism across whole runs already solves better.

## 6. Async, precisely where it belongs

Consistent with `02_Architecture.md` §1's "synchronous core, async periphery" principle: logging, telemetry persistence, and Dashboard serving are asynchronous/non-blocking; the decision-cycle path itself is synchronous, because EnergyPlus is already the thing enforcing that synchrony and adding an async layer on top of an already-blocking call would add complexity without removing any real latency.

## 7. Profiling

- **Python-side**: standard profiling tooling (`cProfile` for one-off analysis, a sampling profiler like `py-spy` for profiling a live, running process without restarting it) applied to the Bridge and Agent Orchestrator specifically — these are the components on the critical path.
- **EnergyPlus-side**: EnergyPlus's own end-of-run timing summary is the first place to look if the *baseline* run itself seems slow, independent of anything this project adds.
- **LLM-side**: the serving stack's own built-in metrics (tokens/second, time-to-first-token, queue depth if serving multiple requests) are the direct measurement of the dominant cost identified in §1 — before optimizing anything else, this is the number to look at.
