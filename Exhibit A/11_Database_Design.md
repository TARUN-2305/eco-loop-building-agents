# 11 — Database Design

## 1. What has to be stored, and how it's actually queried

Two very different access patterns exist in this system, and conflating them is where a lot of database mis-selection comes from:

- **High-frequency, append-only telemetry** (`SensorSnapshot`, once per zone timestep) — write-heavy, rarely read row-by-row, mostly read in aggregate (hourly/daily rollups, comparison queries).
- **Low-frequency, high-value decision records** (`DecisionLog`, `Incident`, once per decision cycle) — much lower volume, but every row matters individually (this is the audit trail behind the "self-correction"/"explainability" rubric criteria) and is sometimes read row-by-row (an operator asking "why did it do that at hour 14?").

Both need to support the Analytics component's comparison queries (`03_Component_Design.md` §7) efficiently: baseline-vs-agent kWh totals and comfort-band-compliance percentages, computed identically for both runs.

## 2. Candidates compared

| Option | What it's good at | Why it's the wrong fit here (or right fit, noted) |
|---|---|---|
| **SQLite** | Zero-ops embedded relational store; ubiquitous, rock-solid, single-file | Good baseline candidate; row-store engine is less efficient than a columnar one for the kind of "aggregate over a whole run" analytical queries this project runs constantly, but perfectly adequate at PoC data volumes. |
| **DuckDB** | Embedded, zero-ops, but **columnar** and built for exactly this kind of analytical aggregation (group-by, window functions over time-series-shaped data), and can query Parquet files directly without an import step | **Chosen as primary** — see §3. |
| **Redis** | Extremely low-latency key-value access; ideal for "what's the current state right now" | Wrong tool for durable historical record — an in-memory store (even with persistence options) is not where you want the one and only copy of your audit trail to live. Retained as an **optional** live-state cache for a real-time dashboard view, not as the source of truth. |
| **InfluxDB** | Purpose-built time-series ingestion and rollups; the 2025 rewrite of its core engine (InfluxDB 3) moved to a columnar Arrow/Parquet-based storage layer and added standard SQL support alongside its original query language, narrowing what used to be its biggest weakness (SQL compatibility) relative to relational alternatives | A strong, legitimate option for a genuinely high-frequency, fleet-scale telemetry problem; over-provisioned for a single-building PoC, and the current open-source tier's database-count/retention limits are exactly the kind of operational constraint not worth taking on for a PoC. Named as a viable production alternative to TimescaleDB, not a wrong choice — just not the one made here (see §4 for the tie-break reasoning). |
| **TimescaleDB** | Postgres extension — full relational SQL, joins against building metadata, and the entire Postgres ecosystem (backup tooling, ORMs, BI tools), with time-series-specific features (hypertables, continuous aggregates) layered on top | **Chosen as the documented production migration target** — see §4. |
| **PostgreSQL (plain, no time-series extension)** | Everything TimescaleDB offers minus the time-series-specific optimizations | Only relevant if TimescaleDB itself isn't available in a given deployment environment; otherwise strictly dominated by TimescaleDB for this workload. |
| **JSON files** | Trivial to write, human-readable | Not queryable at any real speed once you need "total kWh over this run" — every query becomes a full parse-and-scan. Retained only for the Configuration component's own use (`03_Component_Design.md` §10), never as a data store. |
| **Parquet** | Extremely compact, columnar, ideal for long-term archival that will later be read by an analytical engine (including DuckDB directly) | **Chosen as the archival format** for completed-run exports — see §5. |

## 3. Why DuckDB (or SQLite as an acceptable fallback) for the PoC

The PoC's actual requirements are: single-machine, single-writer-mostly (the async buffer from `04_Dataflow.md` §3 is the only writer; Analytics and the Dashboard are read-only), analytically-query-heavy, and zero-ops (no separate database server process to install, configure, and keep alive for a demo). DuckDB satisfies all four better than any server-based option: it's an embedded library (no server process, matching SQLite's operational simplicity), but its columnar engine is specifically built for the "aggregate across many rows" query shape this project runs for every dashboard number, and it can read/write Parquet natively — which directly enables the archival format chosen in §5 without a separate export step. SQLite remains a documented, equally acceptable fallback wherever DuckDB isn't readily available in a given environment; the schema is designed to be portable between the two.

**Explicitly rejected for the PoC, not because they're bad technology, but because they add operational surface with no corresponding benefit at this scale**: standing up a Redis server, an InfluxDB server, or a Postgres/TimescaleDB server purely to store a few megabytes of single-building telemetry is exactly the kind of complexity this project's guiding principle (`00_Project_Overview.md` §1 — pay for production-shaped seams, not production-shaped operational overhead, in this phase) argues against.

## 4. Why TimescaleDB, specifically, as the named production migration target

If this system's data volume or multi-building scope grows past what an embedded store comfortably handles, the tie-break between TimescaleDB and InfluxDB 3 comes down to one thing this project cares about more than raw ingestion throughput: **SQL compatibility with the rest of the stack**. TimescaleDB is a genuine PostgreSQL extension — the same SQL, the same drivers, the same BI/reporting tool compatibility, and the same relational-join capability this project already relies on to relate telemetry to building/zone metadata — with hypertables and continuous aggregates added specifically for time-series workloads. InfluxDB 3's narrowing of the SQL gap makes it a closer call than it would have been a few years ago, and it remains a reasonable choice for a team that's optimizing purely for high-cardinality ingestion throughput at a scale this project doesn't have — but TimescaleDB's full relational-join support against building/zone/config metadata (which this project's schema uses constantly — every telemetry row is joined against zone and run metadata for the comparison queries) is the deciding factor here, not raw benchmark numbers.

## 5. Archival: Parquet

At the end of a run, the complete `SensorSnapshot`/`DecisionLog` tables for that run are exported to Parquet — compact, columnar, and directly queryable by DuckDB (or any other modern analytical engine) without a database server running at all. This gives a clean answer to "how do I look at last month's demo run six months from now": open the Parquet file, no database server dependency required.

## 6. Schema shape (conceptual, not DDL)

| Table | Grain | Key fields |
|---|---|---|
| `runs` | one row per simulation run | `run_id`, `run_mode` (baseline/agent), `idf_name`, `epw_name`, `started_at`, `status` |
| `sensor_snapshots` | one row per zone per timestep | `run_id`, `sim_time`, `zone_id`, `air_temp_c`, `rh_pct`, `pmv`, `ppd_pct`, meter values, `phase` (warmup/run) |
| `decision_logs` | one row per decision cycle | `run_id`, `cycle_id`, `sim_time`, `rationale`, `action_json`, `outcome` (committed/fallback), `trace_json` |
| `incidents` | one row per incident | `run_id`, `cycle_id`, `severity`, `reason`, `raised_at` |
| `run_summaries` | one row per run, written once at run end | `run_id`, `total_kwh`, `pmv_band_compliance_pct`, `pct_cycles_fallback` |

Every table is keyed by `run_id` first, which is exactly what makes FR-9/FR-10 (baseline vs. agent comparison) a `WHERE run_id IN (...)` query rather than a schema difference between two kinds of run.
