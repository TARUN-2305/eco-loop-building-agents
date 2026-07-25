# 14 — Security

## 1. Threat model, stated precisely

This system's actual attack surface in the PoC phase is narrower than a generic "AI agent security" checklist would suggest, and it's worth being precise about why, rather than reflexively listing every possible concern: there is no real multi-tenant surface, no real external user, and no real equipment at risk (`00_Project_Overview.md` §3.2, assumption 6). The threat model that matters here is **not** "an external attacker targets this system," it is **"the LLM itself is an unreliable, semi-adversarial component whose output must never be trusted by default"** — the same posture a well-designed system takes toward any user-supplied input, applied here to a component that happens to be an AI model rather than a human typing into a form.

The one place a *conventional* external-attacker threat model becomes relevant is any external data feed this system consumes — even though the PoC defaults to local, file-derived stubs for weather and utility signals (`00_Project_Overview.md` §3.2), the tool interface is deliberately shaped so a live external feed is a drop-in replacement, and that seam is where real untrusted external content could eventually enter the system.

## 2. Prompt injection

**The concrete risk**: if any tool result ever contains free text sourced from outside this system's own trusted configuration/data (a live weather API's text fields, a scraped utility price page, eventually perhaps occupant-submitted comments in some future extension), that text could contain content crafted to manipulate the LLM into taking an action outside its intended scope.

**Why this system's design already contains the damage, structurally, not just procedurally**:

- The agent's tool set is fixed and small (`09_MCP_Architecture.md`); no tool result — however manipulated its content — can grant the agent a capability it doesn't already have, because there is no mechanism by which a tool *result* expands the tool *set* available to the model. This is the practical version of the MCP specification's own guidance to treat tool annotations and results as untrusted by default.
- Every actuator write passes through `validate_action` and is independently re-checked by `apply_setpoints` itself (`09_MCP_Architecture.md` §2.7) — so even a "successful" injection that convinced the model to *want* to write an unsafe setpoint still cannot actually cause an unsafe actuator write, because that gate does not consult the model's stated intent at all, only the proposed numeric value against the config-loaded bounds.
- Data blocks that originate from outside this system's own trusted config are, in the design, explicitly labeled as data in the prompt structure (not interleaved as if they were instructions), a standard mitigation that reduces (without claiming to eliminate) the chance the model treats embedded content as a command.

The honest summary: this system's defense against prompt injection is **defense in depth that does not depend on the injection failing** — the validator is the backstop specifically because "the model successfully resisted the injection" is not something that can be guaranteed or tested to 100% confidence (§8 of `13_Testing.md` makes the same point about hallucination generally).

## 3. Tool abuse

- **Rate/budget limiting**: a hard cap on tool calls per decision cycle (default 6, `12_API_Design.md`) bounds how much a misbehaving or looping agent can do in one cycle, independent of whether the underlying cause is a bug, a bad prompt, or an adversarial input.
- **Allow-listing, not deny-listing**: the actuator bound table (`01_Requirements.md` SR-2) is a positive allow-list resolved against the actually-loaded `.idf` at startup — an unlisted actuator is unreachable, not merely "not recommended."
- **Every tool call is logged with its full argument set and the `cycle_id` it belongs to** (`09_MCP_Architecture.md` §2.9), which is what makes post-hoc audit ("show me everything the agent tried, not just what it committed") possible — this directly serves both this security chapter and the explainability requirement (FR-13) at the same time, which is not a coincidence: an audit trail that's good enough for debugging is usually also good enough for a security review, and building one trail that serves both is better than building two.

## 4. Simulation safety

- **Bounds are set from physical/comfort reasoning, not just picked arbitrarily**: every actuator's allowed range (SR-1) should be derived from a concrete physical or comfort argument specific to that actuator — e.g., a supply-air temperature setpoint's lower bound kept comfortably above the dew point at expected operating humidity (to avoid condensation risk) and above typical coil-freeze thresholds, not just "somewhere reasonable." This is a modeling exercise that has to be done per building/system configuration, not a number this spec can supply once for every possible model — but the *requirement* that it be done, and be traceable to a stated reason, is universal.
- **Fail-safe defaults, always**: on any uncertainty (validator rejection, timeout, unreachable LLM), the system holds the last known-good or `.idf`-scheduled value — never an extrapolated "best guess," which is the concrete meaning of SR-4.
- **The simulation-only boundary is the load-bearing safety property of this entire phase**, and this document says so explicitly rather than leaving it implicit: every requirement above is written and enforced *as if* real equipment could be damaged, specifically so the architecture does not need to change when it eventually is connected to something real — but nothing in this document should be read as certifying this system safe for that connection. Making that jump would require, at minimum, a staged human-in-the-loop rollout, a real hardware-specific bounds review, and a testing regime well beyond what `13_Testing.md` specifies here; that is future work, tracked explicitly in `16_Risk_Register.md`, not something this Project Bible claims to have already solved.

## 5. Sandboxing, and an anti-pattern this design explicitly rejects

A common failure mode in agentic-AI demo projects is giving the agent a general-purpose "run this shell command" or "edit this file" tool for convenience — usually to let it "self-correct" more flexibly. **This project explicitly does not do that** (SR-3, `01_Requirements.md`): there is no shell tool, no arbitrary file-write tool, and no code-execution tool anywhere in the agent's reach. Every capability is one of the ten named MCP tools in `09_MCP_Architecture.md`, each with a fixed, narrow, schema-typed effect. This is called out explicitly here because it is exactly the kind of shortcut the brief's own "autonomous... without requiring manual code modification" language could tempt a less careful implementation into taking, and it is the single most important thing *not* to add later "just to make debugging easier."

Beyond the tool-level sandboxing, the EnergyPlus process, the LLM inference server, and the MCP server are each recommended to run as separate, minimally-privileged OS processes (containerized, e.g., via Docker, for the PoC) — no component needs, and none should be given, filesystem or network access beyond what its own job requires (the Bridge needs the `.idf`/`.epw` paths and nothing else on disk; the LLM server needs its model weights and nothing on the host filesystem at all; the MCP server needs the Storage file and the config, nothing more).

## 6. Validation, restated as a security control, not just a correctness one

Every boundary in this system — MCP tool input, MCP tool output, config load — is schema-validated, and a validation failure is treated as "reject and surface the error," never "attempt to coerce into something plausible." This matters here for the same reason input validation matters at any trust boundary in any system: silently "helpful" coercion of malformed input is itself a common source of exploitable behavior, and this project takes the position that a loud, explicit rejection is always preferable to a quiet, best-effort guess.
