# Aurora Core FSM - Architectural Baseline State

## [System Overview]
The system, primarily known as **Aurora Core FSM**, is a Federated State Machine architecture designed for algorithmic cryptocurrency trading on Binance Futures. It utilizes real-time order book data, asynchronous event-driven pipelines, and a sophisticated multi-domain layout (located entirely in `apps/reference/domains`) to calculate risk, extract features, and execute trades. The structural backbone leverages **vFoundation**, providing Meta-FSM capabilities, dynamic routing, and Disaster Recovery (WAL, snapshots), while event schemas are governed strictly by global registries located in `apps/reference/dictionaries`. Currently, the system is configured to run in a `hybrid_live_data_testnet_exec` mode.

## [Architecture Topology]

```mermaid
C4Context
    title System Context diagram for Aurora Core FSM

    Person(admin, "Principal Architect/Trader", "Monitors and directs system")

    System_Boundary(base, "vFoundation Core Platform") {
        System_Boundary(app, "Aurora Reference App (apps/reference/domains)") {
            Container(market_data, "Market Data Domain", "Trio/Websockets", "Ingests live order flows and Binance depth events")
            Container(feature_eng, "Feature Engineering", "Pandas/NumPy", "Generates indicators and signals")
            Container(neocortex, "Neocortex", "Python", "Multi-agent dynamic decision making")
            Container(risk_mgmt, "Risk Management", "Python", "Validates dynamic limits (CVaR, inventory)")
            Container(execution, "Execution & Position FSM", "Python (FSM)", "Places/manages/cancels orders & handles brackets")
        }
        Container(dictionaries, "Dictionaries & Event Registry", "YAML", "Central ontology defining verbs, schemas (e.g., verb_registry_v1.yaml)")
    }

    SystemExt(binance, "Binance API", "Mainnet / Testnet Futures")

    Rel(binance, market_data, "Streams order book data (WebSocket)")
    Rel(market_data, feature_eng, "Parsed market ticks/bars")
    Rel(feature_eng, neocortex, "Signals & Features")
    Rel(neocortex, risk_mgmt, "Proposed orders")
    Rel(risk_mgmt, execution, "Approved trades")
    Rel(execution, binance, "Executes API calls (REST/WS)")
    Rel(app, dictionaries, "Validates message ontology during inter-domain routing")
```

## [Tech Stack & Dependencies]
- **Language**: Python (leveraging async/await patterns heavily)
- **Core Framework**: **vFoundation** (acting as FSM-LLM Federated Modular Architecture base)
- **Concurrency Frameworks**: `trio` (async operations) and `fastapi` for metrics / API.
- **Data Engineering**: `pandas` >=2.0.0, `numpy` >=1.24.0
- **Serialization**: `orjson` (fast JSON parsing), `pydantic` v2
- **Config & Ontology**: `PyYAML`, `dotenv`, and centralized YAML verb dictionaries (`apps/reference/dictionaries`)
- **Observability**: `prometheus_client`

## [Hardware & Infrastructure Constraints]
`[REQUIRES USER INPUT: Define local VRAM/RAM/Compute limits here]`

## [Critical Modules (Red Lines)]
These paths manipulate financial state or live orders and are strictly protected.
**[HITL REQUIRED - NO AUTO-COMMITS]**
- `apps/reference/domains/execution_position/fsm.py` (Core FSM Orchestrator)
- `apps/reference/domains/execution_position/fsm_open.py`
- `apps/reference/domains/execution_position/fsm_manage.py`
- `apps/reference/domains/execution_position/fsm_close.py`
- `apps/reference/domains/execution_position/order_guardian.py`
- `apps/reference/domains/execution_position/exposure_guard.py`
- `apps/reference/domains/risk_management/*`

## [Current Technical Debt / Focus]
- **Architecture Synchronization**: Realignment of the system's focus towards `apps/reference/domains` as the sole locus of business logic, explicitly sunsetting/ignoring loosely coupled or legacy implementations like `alysha_core`.
- **Execution Consolidation**: There's ongoing structural audit focus on logic duplication and race conditions within `execution_position` and `order_guardian`, maximizing the native `vFoundation` DR/WAL capabilities for predictability.
- **Async/Sync Complexity**: Potential mixing of async methods in synchronous flows within the FSM pipelines, needing structural validation against the core concurrency practices of `vFoundation`.

---

## CRITICAL VULNERABILITIES IDENTIFIED (HITL REQUIRED)

**Timestamp:** 2026-03-01
**Phase:** Behavioral Forensics Complete — Incident Root Cause Analysis
**Current Drawdown:** -53.1% (Balance: 93.63 USDT)
**Full forensic details:** `execution_journal.md` (H2, H4, H1 sections)

---

### 1. Architectural State Deadlock (H2: NRR-046)
- **Domain:** `decision_making` / `execution_position` (FSM Orchestration)
- **Root Cause:** `_emit_reduce_only_close` (dm.py:3820) and `_handle_regime_flip` (dm.py:2519) call `_propose_trade_intent` without `tf_sec`. The EP-01.3-INT gate at `decision_making.py:3443` strictly requires `tf_sec` to derive `valid_for_ms` for LIMIT orders. Config: `aurora.execution.entry_order_type = "LIMIT"`. All flip/close intents rejected — 10,930 times.
- **Impact:** Infinite NRR-046 rejection loop. Flip positions remain open. Forced SL exits. Causally linked to -53% drawdown.
- **Remediation Target:** Enforce contextual pass-through of `tf_sec` during FSM flip/close operations, OR apply a `close_order_type` policy separate from `entry_order_type`. Create `cmd_close_v1.json` contract. Add regression tests with `entry_order_type = "LIMIT"` in fixture (currently absent from all flip test configs).
- **Key Files:**
  - `apps/reference/domains/decision_making/decision_making.py:2519, 3443, 3820`
  - `apps/reference/domains/execution_position/schemas/cmd_open_v1.json`
  - `tests/domains/decision_making/test_flip_orchestration_v1.py:163`
  - `tests/domains/decision_making/test_regime_flip_close.py:165`

---

### 2. Production Supply Chain Leak (H4: MagicMock)
- **Domain:** `execution_position` (Watchdog / Rate Limiting)
- **Root Cause:** `test_bracket_health_check.py:49` passes full `fsm_config` MagicMock directly to `OrderTimeoutWatchdog(config=fsm_config)`. `MagicMock.__contains__` always truthy → `"rps_limit" in MagicMock()` is True → `self._rps_limit = MagicMock()`. At `watchdog.py:121`: `int(0) < MagicMock()` → `TypeError: '>' not supported between instances of 'MagicMock' and 'int'`. Caught by FSM catch-all → 14 `ADAPTER_ERROR` WAL entries.
- **Impact:** Core FSM event loop crashes during polling. Watchdog polling silently broken in the test context. Secondary risk: `AuroraConfig = MagicMock` ImportError fallback in `conftest.py:9-12` can silently poison all downstream `AuroraConfig()` calls.
- **Production path is safe** — `fsm.py:440` does NOT pass `config=` to the watchdog.
- **Remediation Target:** Fix `test_bracket_health_check.py:49` to not pass root MagicMock as watchdog config dict. Remove `AuroraConfig = MagicMock` ImportError fallback — replace with Fail-Fast. Add `rps_limit` to conftest watchdog fixture.
- **Key Files:**
  - `tests/domains/execution_position/test_bracket_health_check.py:49`
  - `tests/domains/execution_position/conftest.py:9-12, 37-39`
  - `apps/reference/domains/execution_position/watchdog.py:58, 91, 121`

---

### 3. ML Feature Starvation & Silent Failure (H1: ta_ensemble)
- **Domain:** `alpha_search`
- **Root Cause:** `ta_ensemble` (ensemble_3_models) is wired to `EVT:FEATURES_CALCULATED` from the Aurora microstructure pipeline (`obi`, `tfi`, `delta_price`, `ema_bias`, etc.). Its 3 TA models require entirely different computed indicators (`rsi_14`, `bb_position`, `macd_signal`, `stoch_k`, `atr_ratio`, `realized_volatility_1h`, `price_momentum_5m`, etc.) that are never calculated anywhere. Models use `.get(key, default)` with neutral defaults → score=0.0 with confidence≥0.3 per bar, legitimately. `EnsembleModel.get_required_features()` returns `[]` (base class, not overridden) → pre-call gate at `backtest_plugin.py:388` never fires.
- **Impact:** Score = 0.0 for 100% of inferences (9,104/9,104). No signals above `threshold=0.18`. Virtual trader opens 0 positions. Weight rebalancing permanently frozen (no PnL feedback loop). `except Exception: continue` at `ensemble.py:201` silently swallows any future crashes — indistinguishable from neutral-input run.
- **Remediation Target:** Either (A) implement a TA indicator computation stage that transforms OHLCV bar data into `rsi_14`, `bb_position`, etc. before passing to ta_ensemble, OR (B) deprecate TA models and replace with microstructure-native models. Override `EnsembleModel.get_required_features()`. Replace `except Exception: continue` with structured logging + telemetry counter.
- **Key Files:**
  - `apps/reference/domains/alpha_search/backtest_plugin.py:388-396`
  - `apps/reference/domains/alpha_search/ensemble.py:77, 136-145, 181-213`
  - `apps/reference/domains/alpha_search/models/momentum.py`
  - `apps/reference/domains/alpha_search/models/mean_reversion.py`
  - `apps/reference/domains/alpha_search/models/volatility.py`
  - `config/alpha_search.yaml`
