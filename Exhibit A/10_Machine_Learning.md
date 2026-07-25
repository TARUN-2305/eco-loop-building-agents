# 10 — Machine Learning

## 1. The test applied to every candidate use case

A supervised or learned model earns its complexity cost in this system only when all three hold:

1. **The relationship isn't already known analytically or physically.** If a validated closed-form model exists (thermal comfort, psychrometrics), a learned approximation adds approximation error and opacity for no accuracy gain.
2. **Enough representative data actually exists** to fit the model without it just memorizing or overfitting a single building/season.
3. **The accuracy improvement, if any, is large enough to justify the added complexity, latency, and failure surface** — a model is a new thing that can be wrong, silently drift, or need retraining; that cost has to be paid for with a real benefit.

Six candidate uses from the brief are evaluated against this test below.

## 2. Occupancy prediction — **not built, with cited justification, not just intuition**

For this PoC, occupancy is already deterministically known from the `.idf`'s own schedule objects — there is no sensor uncertainty to predict *away*, because the "ground truth" occupancy is exactly what the schedule says it is. A prediction model here would be predicting a number the simulation already hands over for free.

Even setting the PoC's specific situation aside, there is a direct, relevant finding in the building-controls literature that occupancy *prediction* specifically is often not where the energy-saving leverage is: a study examining the value of occupancy information for building climate control (Oldewurtel, Sturzenegger, and Morari, *Applied Energy*, 2013) concluded that long-horizon occupancy forecasting did not produce meaningful additional energy savings in their simulation study, and that most of the achievable savings from occupancy-awareness came from simple **reactive** setback (cutting lighting/ventilation promptly once absence is detected), not from forecasting absence in advance. That is a real, citable reason — not just "it's out of scope for the PoC" — to skip investing in an occupancy-prediction model here: the evidence suggests the reactive case (which this system already handles via its normal decision cycle observing current, not predicted, occupancy) captures most of the value, and the harder, more failure-prone forecasting piece would be chasing a smaller remaining gain.

**Verdict**: not built. If this system is ever pointed at a *real* building with real occupancy sensors and genuine uncertainty, a simple presence-detection reactive rule (which needs no ML) should be tried and evaluated before a predictive model is considered at all, precisely because of the finding above.

## 3. Demand (peak load) prediction — **conditionally useful, classical methods sufficient**

A short-horizon demand forecast (next few hours of facility electrical draw) has real, direct value for the objective in `06_Control_System.md` §3 — a peak-demand constraint is only actionable if the optimizer can see it coming. But this does not require deep learning: a gradient-boosted or even linear regression model against a handful of features (time of day, day type, outdoor temperature, recent trailing load) is standard practice and appropriate at this data volume (one building's worth of simulation history, not a fleet).

**Verdict**: a lightweight classical regression model is a reasonable, low-risk addition **if** the peak-demand constraint (EC-2) is enabled for a given run; it is not required for the core comfort/energy loop and should not be built as a deep model regardless — there simply isn't enough data from a single-building PoC to justify one, and a simple model that's easy to inspect and debug is a better fit for a system whose other stated priority is auditability.

## 4. Weather prediction — **out of scope by construction, not by ML judgment**

This is not a "should ML be used" question for the PoC at all: the simulation is driven by a fixed EPW file, and the `get_weather_forecast` tool (`09_MCP_Architecture.md`, §2.2) deliberately reads *ahead* in that same file rather than predicting anything, because inventing forecast uncertainty that the simulation itself doesn't model would make the demo's baseline-vs-agent comparison harder to interpret, not more realistic. A live weather API (with genuine forecast uncertainty, and therefore a genuine role for a weather-prediction model or at least published NWP forecasts) is a named, swappable extension (`00_Project_Overview.md` §3.2) but is not part of this phase.

## 5. Anomaly detection — **useful, but a statistical method, not a deep model**

Flagging a sensor reading or a simulation output that's inconsistent with recent normal behavior has clear value here: it's a cheap, general-purpose backstop that can catch a misconfigured actuator, a stuck sensor, or an EnergyPlus-side warning condition before it shows up as a comfort or energy problem three cycles later. At this data volume and this problem's shape (single-variable or low-dimensional thresholding against recent trailing behavior), a simple statistical control-chart style method (rolling z-score / exponentially weighted moving average against recent history) does the job with no training step, no drift-monitoring burden, and full interpretability ("this reading is 4 standard deviations from the last day's mean" is immediately actionable in a way a black-box anomaly score is not).

**Verdict**: built, but deliberately as a statistical method, not a learned model — this is a case where reaching for "AI" would be over-engineering relative to the problem's actual difficulty and this project's own data volume.

## 6. Comfort prediction — **explicitly rejected in favor of the existing analytical model**

PMV/PPD (Fanger's model, standardized in ISO 7730 and referenced by ASHRAE 55) is already a validated, decades-old, physics-grounded model with known applicability bounds — precisely the "relationship is already known analytically" case that fails test #1 in §1 above. Replacing it with a learned comfort model would trade a well-understood, auditable calculation for an opaque one, for no accuracy benefit in this PoC's context (a simulated population-level comfort index, not real occupants with individual, learnable preferences).

**Verdict**: not built. Personalized comfort modeling (learning an individual occupant's actual preference deviation from the population-level PMV model) is a legitimate, actively published research direction — but it requires real individual feedback data this PoC has no way to collect (there are no real occupants), so it fails test #2 as much as it fails to be motivated by test #1. Named as future work, not attempted here.

## 7. Energy forecasting (short-horizon, feeding the optimizer's lookahead) — **a simple model is reasonable; deep learning is explicitly rejected**

A short lookahead on expected energy draw under a candidate setpoint trajectory is exactly what `propose_setpoints`' bounded-horizon evaluation needs, and a low-complexity model (comparable to the demand-prediction case in §3, or even a physics-informed reduced-order estimate derived directly from recent zone-level meter and temperature data) is appropriate. Deep sequence models (LSTM/Transformer-style forecasters), which show up frequently in the published literature for *fleet-scale or long-horizon* load forecasting, are explicitly rejected for this project's scope: they need substantially more training data than a single building's PoC-length simulation history can provide, they carry real overfitting risk at this data volume, and — again — a simpler, more inspectable model serves this project's auditability priority better for a marginal (if any) accuracy gain that hasn't been demonstrated at this scale.

## 8. Summary table

| Use case | Built? | Method if built | Core reason |
|---|---|---|---|
| Occupancy prediction | No | — | Already known from schedule; literature suggests reactive setback captures most of the value anyway |
| Demand prediction | Conditional | Classical regression (GBM/linear) | Real value if peak constraint enabled; deep learning unjustified at this data volume |
| Weather prediction | No | — | Out of scope; EPW file read-ahead used instead |
| Anomaly detection | Yes | Statistical control-chart (rolling z-score/EWMA) | Cheap, interpretable, matches problem's actual dimensionality |
| Comfort prediction | No | Analytical PMV/PPD (Fanger/ISO 7730) used instead | Already solved analytically; no real-occupant data to learn from anyway |
| Energy forecasting (short-horizon) | Conditional | Simple regression / reduced-order estimate | Feeds the optimizer's lookahead; deep sequence models rejected at this data scale |

The pattern across every "no" and "conditional, simple" verdict above is the same: this project treats "use an LLM agent for supervisory reasoning" and "use machine learning for every sub-problem" as two different decisions, and refuses to let the first one drag the second one along by default.
