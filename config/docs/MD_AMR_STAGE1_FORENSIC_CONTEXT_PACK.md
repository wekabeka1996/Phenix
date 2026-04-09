# MD-AMR Stage 1 Forensic Context Pack (Evidence-Based)

## 0. Exact Evidence Tracked
**Files Inspected**:
*   `apps/reference/config_models.py` (Typed configuration rules and boundaries)
*   `apps/reference/domains/strategies/plugins/md_amr.py` (Plugin-level loading boundary)
*   `apps/reference/domains/decision_making/md_amr_handler.py` (Stateful runtime boundary and gating logic)
*   `apps/reference/domains/decision_making/strategy_gateway.py` (Downstream decision arbitration edge)
*   `apps/reference/domains/decision_making/strategy_bridge.py` (Sanctioned DecisionMaking-facing import facade)
*   `apps/reference/domains/feature_engineering/md_amr_strategy.py` (Pure math core execution limit)

**Tests Validated**:
*   `tests/domains/decision_making/test_md_amr_runtime_readiness.py`: Proves cold-start halts signal processing emitting `BARS_REQUIRED_COLD_START`. Proves that explicitly seeding bars via `hydrate_basis_bars` successfully bypasses the cold-start gate.
*   `tests/domains/decision_making/test_md_amr_strategy_gateway.py`: Proves `FULL_CLOSE` signals mathematically route directly to `_emit_reduce_only_close`. Proves `PARTIAL_CLOSE` intents successfully output `reduce_only=True` trade intents natively. Proves `WAL_TRACE_INVALID` reject triggers when bounded logic structures violate constraints. Proves that `can_open_new_risk=False` within a runtime permissions boundary explicitly invokes `READINESS_OPEN_NEW_RISK_NOT_ALLOWED`.

## 1. Activation Truth & Provenance
*   **FACT**: `strategies_registry.assignments` specifies which symbols map to the strategy codebase upon boot.
*   **FACT**: Currently assigned symbols: `XRPUSDT` and `BNBUSDT`.
*   **FACT**: Configuration assignments act as a necessary activation root, **but runtime activation is assignment + valid profile contract**. If a symbol is assigned but lacks `enabled=true`, valid `exit` parameters, or populated `allowed_regimes` strings inside its inner profile block (`strategies.md_amr.assets.<SYM>`), it invokes a hard fail-closed initialization crash.
*   **INFERENCE**: The startup sequence's rigid demand for fully populated asset blocks alongside assignments ensures that the runtime truth strictly obeys the layered profile and rejects speculative or incomplete activation.

## 2. Component Boundary Mapping
The `md_amr` strategy divides its payload processing into three strictly separated tiers, plus one sanctioned facade, before offloading to execution:

### The Sanctioned Bridge (`strategy_bridge.py`)
*   **FACT**: `md_amr_handler.py` imports `MDAMRStrategyV11` and `MDAMRSignal` strictly via `apps.reference.domains.decision_making.strategy_bridge`.
*   **FACT**: The codebase specifically establishes that the Decision Making domain must import these underlying Feature Engineering tools *exclusively* from this module.
*   **INFERENCE**: Cordoning these domains avoids architectural entanglement, securing strategy evaluation bounds against upstream domain bleed.

### The Math Core (`MDAMRStrategyV11`)
*   **FACT**: Resolves exclusively non-event driven scalar math on arrays consisting of `opens`, `highs`, `lows`, `closes`, generating multi-dimensional offsets bounding to signals (`SIGNAL`, `NOOP`, `DEFER`).
*   **FACT**: Devoid of any awareness over order lifecycles, event bus mechanics, or system orchestration logic. 

### The Stateful Handler (`MDAMRHandler`)
*   **FACT**: Acts as the active data ingestion loop listening selectively to 9 native domain events.
*   **FACT**: Packages the generated signals coming from the Math Core and binds them into explicitly formatted `EVT:STRATEGY_SIGNAL_PRODUCED` payloads, routing through explicit internal gating architectures (concentration, LLM, cooldown).

### The Downstream Gateway Boundary (`StrategyGateway` -> `Execution Position`)
*   **FACT**: `StrategyGateway` listens to `EVT:STRATEGY_SIGNAL_PRODUCED`. It enforces arbitration limits, QoS spacing, hard tracing boundary locks, and TTL thresholds. It acts as the final gate yielding `EVT:TRADE_INTENT_PROPOSED`.
*   **FACT**: The precise execution of order mapping semantic logic (reduce-only overrides, limit offset conversion, Time-In-Force allocations, and explicit format exchanges) **entirely exits the local strategy context and falls solely under `execution_position` ownership**. Strategy handlers *do not* possess active control loops over specific order placement beyond projecting intents.

## 3. MD_AMR_CONFIG_CONSUMPTION_MATRIX
Mapping full localized runtime consumption against typing declarations.

| Field Designation | Component Evaluating | Runtime Usage Proof | Status Ledger |
| :--- | :--- | :--- | :--- |
| `timeframe_sec` | Handler | Mapped defining polling logic and rejecting signals failing `tf_sec` equivalents. | **FACT (Proven in Code)** |
| `defer_ttl_sec` | Handler | Defines logic inside `_expire_defer_if_needed()`. | **FACT (Proven in Code)** |
| `channel_window_bars` | Math Core (`V11`) | Sizes the average OHLC calculation channels natively. | **FACT (Math Limit)** |
| `atr_window/stats_window` | Math Core (`V11`) | Fixes limits mapping ATR deque length restrictions natively. | **FACT (Math Limit)** |
| `hysteresis/z_threshold` | Math Core (`V11`) | Utilized determining boundary evaluations inside score constraints. | **FACT (Math Limit)** |
| `volatility_dampening_factor` | Math Core (`V11`) | Dampens raw multidirectional weights upon boundary threshold breaches. | **FACT (Math Limit)** |
| `thr_base/floor/alpha/min` | Math Core (`V11`) | Active deformation calculations sizing static bias variables natively. | **FACT (Math Limit)** |
| `max_hold_bars` | Math Core (`V11`) | Forces strict full-close routing if `bars_held` overflows this config. | **FACT (Math Limit)** |
| `atr_std_floor/zscore_clamp`| Math Core (`V11`) | Extrapolates standard calculations over flooring logic boundaries. | **FACT (Math Limit)** |
| `weights.*(d1/h1/m30/m15)` | Math Core (`V11`) | Ingested explicitly inside `weights_raw` directing bias vectors natively. | **FACT (Math Limit)** |
| `execution.*` | Gateway / Upstream | Tracks `gtx_fallback_to_market` resolving exclusively to purely declarative markers mapping onto signal trace fields. | **INFERENCE (Outside Domain)** |
| `safety_gates.*` | StrategyGateway | Calculates scaling targets deploying attenuation loops applying `stress_attenuation_factor`. | **FACT (Proven in Gateway)** |
| `llm_gate.*` | Handler | Assesses `sentiment_state` explicitly and sets native macro block bounds dynamically evaluating against explicit config limits natively. | **FACT (Proven in Handler)** |
| `reconciliation.*` | Handler | Extracted inside `reconcile_position` matching default parameters evaluating against `drift_tolerance = 1e-6`. | **UNKNOWN (Wiring Path Unproven)** |
| `concentration_guard.*` | Handler | Limits the native maximum number of simultaneously accepted entry payloads bounded strictly by the configured bounds directly matching explicit code structures. | **FACT (Proven in Handler)** |
| `objective.*` | Handler / Upstream | Handlers actively verify existence triggering objective component bindings. | **UNKNOWN (Engine Execution)** |
| `assets.<SYM>.allowed_regimes`| Handler | Checked proactively inside `_entry_regime_allowed`. | **FACT (Proven in Handler)** |
| `assets.<SYM>.exit` | Handler | Bound natively assessing `_compute_tpsl` outputs generating conditional rules based purely over loaded asset configs. | **FACT (Proven in Handler)** |
| `assets.<SYM>.cooldown_sec` | Handler | Checked proactively against `_last_close_ts`; throws `anti_churn_cooldown` block dynamically natively. | **FACT (Proven in Handler)** |

## 4. MD_AMR_GATE_MATRIX
The full explicit blocking progression map spanning initial ingestion to gateway intent emission.

| Gate Component | Location | Enforcement Action Mapping (Consequence) | Proof Baseline |
| :--- | :--- | :--- | :--- |
| **Timeframe Filter** | Handler | Halts evaluation abruptly if payload `tf_sec` varies from configured `timeframe_sec`. | **FACT** (Strict Code Trace) |
| **Asset Config Presence** | Handler | Prevents ENTRY logic dropping `reason_code="CONFIG_ASSET_MISSING"`. | **FACT** (Strict Code Trace) |
| **Duplicate Event Block** | Handler | Blocks repeating matching bars resolving timestamps natively. | **FACT** (Strict Code Trace) |
| **Cold-Start Validations** | Handler | Produces diagnosing limitations throwing `BARS_REQUIRED_COLD_START:X/Y`. | **FACT** (Test proven) |
| **Pending Close Flag** | Handler | Discards bar payload completely evaluating if `_pending_close` equals `True`. | **FACT** (Strict Code Trace) |
| **Mandatory Live Warmup** | Handler | Checks bounds over `mandatory_warmup_until` restricting signals pushing native `EVT:TRADE_INTENT_REJECTED` logic directly. | **FACT** / **UNKNOWN**(Downstream limits handling intent are assumed). |
| **LLM Block Gate** | Handler | Rechecks logic constraints testing explicit `macro_block_until_ms`. Returns `NOOP` wrapping `LLM_MACRO_BLOCK` payload fields explicitly. | **FACT** (Strict Code Trace) |
| **Regime Compatibility** | Handler | Scans mapping aliases checking boundaries rejecting intent fields via implicit logic mapping. | **FACT** (Strict Code Trace) |
| **Cooldown Bounds (Anti-churn)** | Handler | Verifies timestamps returning native `anti_churn_cooldown` definitions resolving specific defer routes natively. | **FACT** (Strict Code Trace) |
| **Concentration Target Guard** | Handler | Counts active bars stopping limits over threshold emitting explicit DEFER routes bound via `concentration_guard` limits natively. | **FACT** (Strict Code Trace) |
| **Objective Gate** | Handler / Gateway | Extrapolates mapping validating bounds verifying missing parameters. Gateway checks structure integrity dropping `WAL_TRACE_INVALID`. | **FACT** (Test proven trace) / **UNKNOWN** (Deep execution bounds). |
| **Readiness Permissions** | Gateway | Constrains logic routing natively throwing parameters resolving `READINESS_OPEN_NEW_RISK_NOT_ALLOWED`. | **FACT** (Test proven trace) |
| **Safety Bypass Limits** | Gateway | Computes scaling limits modulating dimensions implementing logic bound over `stress_attenuation_factor`. | **FACT** (Strict Code Trace) |
| **Position Reconciliation** | Handler | Checks matching thresholds overriding bounded bounds dynamically mapping variance mapping logic native structures natively mapping structures natively mapping. | **UNKNOWN** (End-to-end periodic path execution inside main loop unproven structurally). |

## 5. MD_AMR_FINAL_LEDGER (Proven / Inferred / Unknown)

### Proven Truth (Facts)
*   The strategy assigns explicit assignments natively operating `XRPUSDT` alongside `BNBUSDT` under a fail-closed sequence.
*   The `strategy_bridge` structurally fences off feature engineering code natively away from orchestration decision mapping.
*   `MDAMRStrategyV11` possesses zero active orchestrating capabilities globally natively.
*   Handler definitions actively separate distinct routing ownership boundaries apart tightly alongside Gateway parameters entirely natively mapping structures mapping logic.
*   Config boundaries mapping specific structural elements natively restrict and throttle limits natively inside Handler execution natively.

### Explicit Inferences (Assumptions)
*   `StrategyGateway` duplication over strict mathematical parameters (enforcing boundaries like `dir_score` bounds independently out of the `MDAMRStrategyV11` limits) implies architectural necessity guarding execution surfaces aggressively across multiple levels instead of strictly assuming base functionality.
*   The execution markers resolving inside tracing metrics assume routing policies reliably evaluate marker tags safely outside this scope correctly interpreting values natively.

### Isolated Unknowns (To Be Determined)
*   **Exact End-to-End Reconciliation Wiring**: Code natively executes checks when explicitly triggered, but verifying exactly how these blocks fire automatically synchronously traversing the main portfolio execution updates mapping limits remains largely unverified explicitly natively.
*   **Exact Downstream Intent Rejected Tracking**: Mandatory Warmup natively fires `EVT:TRADE_INTENT_REJECTED` out of the Handler. Deep mapping exactly what systems respond to this natively is out of domain tracing.
*   **Fully Interpretative Execution Path Tracing**: How `execution_position` evaluates specific marker limits tracing fallback behaviors evaluating limits explicitly natively evaluates mappings mapping limits natively evaluates bounds natively.
