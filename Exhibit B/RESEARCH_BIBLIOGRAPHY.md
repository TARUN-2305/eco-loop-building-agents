# RESEARCH_BIBLIOGRAPHY.md

Every entry below was either verified directly against a primary/official source or is a well-established, widely-corroborated citation (cross-confirmed across multiple independent secondary sources during research for this Project Bible). Where full author-list precision could not be independently confirmed, the entry says so rather than presenting a guessed list as fact. Blogs and non-authoritative aggregator sites are excluded except where explicitly labeled as such (the DeepMind cooling case, §5, is deliberately kept as an example of a source this project treats with appropriate caution, not as an unlabeled peer-reviewed claim).

---

## EnergyPlus

### Runtime API

- **"EnergyPlus Runtime API" / "Python API" documentation.** NREL / U.S. Department of Energy (ongoing, versioned with each EnergyPlus release; current release referenced throughout this Project Bible: 26.2). *Why it matters*: this is the primary source for `EnergyPlusAPI`, `api.runtime` callback registration, and `api.exchange` sensor/actuator access — the entire integration layer this project is built on. *Supports*: ADR-002, `07_EnergyPlus_Design.md` in full.

### Engineering Reference

- **"EnergyPlus Engineering Reference."** NREL / U.S. Department of Energy (ongoing, versioned). *Why it matters*: the authoritative source for the underlying heat-balance and HVAC-system physics EnergyPlus computes each timestep — the ground truth against which this project's PMV inputs (air temperature, mean radiant temperature) are understood. *Supports*: `07_EnergyPlus_Design.md`, `10_Machine_Learning.md` §6.

### Input Output Reference

- **"EnergyPlus Input Output Reference."** NREL / U.S. Department of Energy (ongoing, versioned). *Why it matters*: defines every `.idf` object this project reads or writes, including `EnergyManagementSystem:Actuator`-adjacent concepts and the schedule/setpoint-manager objects the Bridge actuates around. *Supports*: ADR-002, `07_EnergyPlus_Design.md` §3–4, `idf_tools/` module design.

### Python API (library-level)

- **`eppy`** (Santosh Philip and contributors), open-source Python library for programmatic `.idf` reading/editing. *Why it matters*: the standard, well-established tool for offline `.idf` manipulation, used here exclusively for FR-11's ECM sweep — never for runtime control. *Supports*: ADR-001, ADR-002, `07_EnergyPlus_Design.md` §4.

---

## ASHRAE

### Thermal comfort

- **ANSI/ASHRAE Standard 55-2023, *Thermal Environmental Conditions for Human Occupancy*.** ASHRAE. *Why it matters*: defines the acceptable PMV/PPD comfort band this project's comfort constraints (CC-1, CC-2) are drawn from, and the elevated-air-speed applicability limits `compute_pmv`'s input validation checks against. *Supports*: CC-1–3, ADR-010, `06_Control_System.md` §3.

### PMV

- Fanger, P.O. (1970). *Thermal Comfort: Analysis and Applications in Environmental Engineering.* Danish Technical Press. *Why it matters*: the original analytical derivation of the PMV/PPD model this project's `compute_pmv` tool implements verbatim, rather than approximating with a learned model. *Supports*: ADR-010, FR-3.
- **ISO 7730:2005**, *Ergonomics of the thermal environment — Analytical determination and interpretation of thermal comfort using calculation of the PMV and PPD indices and local thermal comfort criteria.* International Organization for Standardization. *Why it matters*: standardizes Fanger's model and defines the graduated comfort categories (±0.2/±0.5/±0.7 PMV) this project's tiered target/hard comfort bands (CC-1/CC-2) are modeled on. *Supports*: CC-1, CC-2.

### HVAC controls (predictive and learning-based)

- Oldewurtel, F.; Parisio, A.; Jones, C.N.; Gyalistras, D.; Gwerder, M.; Stauch, V.; Lehmann, B.; Morari, M. (2012). "Use of model predictive control and weather forecasts for energy efficient building climate control." *Energy and Buildings*, 45, 15–27. *Why it matters*: one of the founding empirical comparisons of MPC against classical building control, cited throughout the MPC literature this project relies on. *Supports*: `06_Control_System.md` §1.3.
- Drgoňa, J.; Arroyo, J.; Cupeiro Figueroa, I.; Blum, D.; Arendt, K.; Kim, D.; Ollé, E.P.; Oravec, J.; Wetter, M.; Vrabie, D.L.; Helsen, L. (2020). "All you need to know about model predictive control for buildings." *Annual Reviews in Control*, 50. *Why it matters*: the synthesis source for this project's stated 15–50% MPC energy-savings range, and the primary reference for why MPC's core idea (bounded-horizon optimization) is retained inside `propose_setpoints` even though MPC alone is rejected as the sole control strategy. *Supports*: ADR-005, `06_Control_System.md` §1.3, §2.
- Mason, K.; Grijalva, S. (2019). "A review of reinforcement learning for autonomous building energy management." *Computers & Electrical Engineering*, 78, 300–312. *Why it matters*: source for this project's stated RL savings ranges (~10% HVAC, ~20% water heating, >20% whole-building) and for the observation that RL's realized savings are more variable across applications than MPC's. *Supports*: `06_Control_System.md` §1.4.
- Wang, Z.; Hong, T. (2020). "Reinforcement learning for building controls: The opportunities and challenges." *Applied Energy*, 269, 115036. *Why it matters*: a widely-cited review specifically flagging the simulation-vs-field-deployment gap in the RL-for-buildings literature — the direct evidentiary basis for this project's caution about relying on RL as the primary real-time control mechanism. *Supports*: ADR-005, `06_Control_System.md` §1.4.
- Arroyo, J.; Manna, C.; Spiessens, F.; Helsen, L. (2022). "Reinforced model predictive control (RL-MPC) for building energy management." *Applied Energy*, 309, 118346. *Why it matters*: a directly relevant precedent for this project's own hybrid (deterministic-core + learned-supervisor) philosophy, demonstrating that combining MPC's constraint satisfaction with RL's adaptability outperforms either alone. *Supports*: ADR-005, `06_Control_System.md` §2, named future-work direction.
- Oldewurtel, F.; Sturzenegger, D.; Morari, M. (2013). "Importance of occupancy information for building climate control." *Applied Energy*, 101, 521–532. *Why it matters*: the specific evidentiary basis for this project's decision *not* to build an occupancy-prediction model — the paper's finding that reactive setback captures most of the achievable savings, with long-horizon occupancy forecasting adding comparatively little. *Supports*: ADR (implicit in `10_Machine_Learning.md` §2), the "Occupancy prediction: not built" verdict.
- Evans, R.; Gao, J. (2016). "DeepMind AI Reduces Google Data Centre Cooling Bill by 40%." Google/DeepMind engineering blog post (not peer-reviewed). *Why it matters, and why it's flagged*: the most widely cited real-world RL-for-infrastructure result, and deliberately presented in this Project Bible as a corporate announcement rather than a peer-reviewed finding — the distinction matters because it directly motivates this project's insistence on a deterministic validator regardless of how well an AI-driven controller appears to perform. *Supports*: `06_Control_System.md` §1.4 (cited with its provenance caveat intact).
- Lazic, N. et al. (2018). "Data center cooling using model-predictive control." NeurIPS Workshop paper (full author list not independently re-verified for this bibliography beyond the lead author — cite the original NeurIPS 2018 workshop proceedings directly before relying on the complete author list). *Why it matters*: the peer-reviewed follow-up to the 2016 blog post, notable for deliberately adopting a safety-constrained, model-based approach rather than end-to-end model-free RL — direct precedent for this project's own refusal to let an LLM (or any learned component) act without a deterministic safety gate. *Supports*: ADR-005, `06_Control_System.md` §1.4, `14_Security.md`.

---

## LLMs

### ReAct

- Yao, S.; Zhao, J.; Yu, D.; Du, N.; Shafran, I.; Narasimhan, K.R.; Cao, Y. (2023). "ReAct: Synergizing Reasoning and Acting in Language Models." *International Conference on Learning Representations (ICLR) 2023* (arXiv:2210.03629). *Why it matters*: the foundational interleaved reasoning-and-acting pattern this project's per-cycle Agent Orchestrator loop is built on. *Supports*: ADR (implicit in `08_LLM_and_Agent_System.md` §3), `agent/orchestrator.py`'s core control flow.

### Reflexion

- Shinn, N.; Cassano, F.; Gopinath, A.; Narasimhan, K.; Yao, S. (2023). "Reflexion: Language Agents with Verbal Reinforcement Learning." *Advances in Neural Information Processing Systems (NeurIPS) 2023*, vol. 36, pp. 8634–8652. *Why it matters*: the Actor/Evaluator/Self-Reflection pattern this project's once-per-simulated-day reflection mechanism is modeled on, converting outcome feedback into verbal lessons without weight updates. *Supports*: `08_LLM_and_Agent_System.md` §3, `agent/memory.py`'s reflection-summary design.

### Function Calling

- Schick, T.; Dwivedi-Yu, J.; Dessì, R.; Raileanu, R.; Lomeli, M.; Hambro, E.; Zettlemoyer, L.; Cancedda, N.; Scialom, T. (2023). "Toolformer: Language Models Can Teach Themselves to Use Tools." *NeurIPS 2023* (arXiv:2302.04761). *Why it matters*: the foundational demonstration that LLMs can learn to invoke external tools for exactly the functions (arithmetic, precise computation) they are unreliable at natively — the direct conceptual justification for delegating `propose_setpoints`'s arithmetic to a deterministic tool rather than LLM token generation. *Supports*: ADR-005, `06_Control_System.md` §1.5.

### Structured Outputs

- vLLM project documentation, "Structured / Guided Decoding" (vLLM maintainers, ongoing). *Why it matters*: primary source for this project's chosen mechanism (grammar/JSON-schema-constrained decoding) for guaranteeing syntactically valid tool calls. *Supports*: ADR-008.
- XGrammar project (contributors from CMU, MLC, and NVIDIA), grammar-constrained-decoding engine documentation. *Why it matters*: representative of the current generation of high-performance constrained-decoding backends this project's serving-stack requirement (ADR-004, ADR-008) assumes availability of. *Supports*: ADR-008.

### Prompt Engineering

- Wei, J. et al. (2022). "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models." *NeurIPS 2022*. *Why it matters*: the general technique this project's per-cycle reasoning step relies on for the LLM to articulate its objective-weighting rationale before calling `propose_setpoints`. *Supports*: `08_LLM_and_Agent_System.md` §2–3, prompt template design in `agent/llm_client.py`.
- Liu, N.F. et al. (2023/2024). "Lost in the Middle: How Language Models Use Long Contexts." *Transactions of the Association for Computational Linguistics (TACL)*. *Why it matters*: the evidentiary basis for this project's rejection of a long-context-only memory design in favor of the two-tier rolling-window-plus-reflection approach. *Supports*: `08_LLM_and_Agent_System.md` §3, `15_Performance.md` §3.

---

## MCP (Model Context Protocol)

### Official specification

- Model Context Protocol specification, revision **2025-11-25** (current at time of writing), with revision **2026-07-28** in release-candidate status. Anthropic / MCP steering committee, published at modelcontextprotocol.io. *Why it matters*: the authoritative source for the tools/resources/prompts primitives, the JSON-RPC 2.0 message format, and the protocol-vs-execution error distinction this project's entire tool layer depends on. *Supports*: ADR-003, `09_MCP_Architecture.md` in full.

### SDK

- Official MCP SDKs (Python, TypeScript), maintained under the `modelcontextprotocol` organization. *Why it matters*: the reference implementation this project's `mcp_server/` module is built against rather than a hand-rolled JSON-RPC layer. *Supports*: ADR-003, `mcp_server/server.py`.

### Transport

- MCP specification, Transports section — stdio and Streamable HTTP (the latter superseding the deprecated HTTP+SSE transport in the mid-2025 revision cycle). *Why it matters*: the direct source for this project's transport choice (stdio for the PoC) and its documented upgrade path (Streamable HTTP for a multi-host deployment). *Supports*: ADR-003, `09_MCP_Architecture.md` §1.

### Security

- MCP specification, security and trust guidance (tool-annotation trust model; the recommendation to treat tool outputs as untrusted by default). *Why it matters*: the direct source for this project's "never let a tool's output silently expand agent capability" design pattern. *Supports*: `14_Security.md` §2, `09_MCP_Architecture.md` §1.

---

## Database

### DuckDB

- DuckDB project documentation (DuckDB Foundation / DuckDB Labs, ongoing). *Why it matters*: primary source for DuckDB's embedded, columnar, analytical-query-optimized design and its native Parquet interoperability — the basis for choosing it as this project's primary PoC store. *Supports*: ADR-006, `11_Database_Design.md` §3.

### SQLite

- SQLite documentation, "Appropriate Uses For SQLite" (SQLite Consortium, ongoing). *Why it matters*: the authoritative source on SQLite's embedded, zero-configuration, single-file design — the basis for treating it as an equally acceptable fallback wherever DuckDB isn't readily available. *Supports*: ADR-006, `11_Database_Design.md` §2–3.

### TimescaleDB

- TimescaleDB (TigerData) documentation — hypertables, continuous aggregates, and full PostgreSQL/SQL compatibility (ongoing; note the "Timescale" → "TigerData" corporate rebrand as of mid-2025). *Why it matters*: the direct source for this project's production-migration recommendation, specifically the relational-join capability against building/zone metadata that this project's schema depends on. *Supports*: ADR-006, `11_Database_Design.md` §4.

---

## Performance

### KV Cache / Prompt Caching

- vLLM project documentation, "Automatic Prefix Caching." *Why it matters*: the concrete mechanism this project's "static system prompt + tool schemas as a stable prefix" design (`15_Performance.md` §2) is built to exploit. *Supports*: `08_LLM_and_Agent_System.md` §2, `agent/llm_client.py` prompt-construction rules.

### Structured Decoding

- (See "Structured Outputs" above — vLLM and XGrammar entries apply identically here; listed once to avoid duplicate-source padding per this bibliography's own citation discipline.)

---

## Bibliography discipline note

Consistent with the copyright and accuracy norms this whole Project Bible follows: every finding above is paraphrased in this project's own words, not quoted from any source; where a full author list could not be independently confirmed to this document's own satisfaction (the Lazic et al. 2018 entry), that uncertainty is stated rather than presented as verified fact.
