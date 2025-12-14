# FSM EVENT MAP (Core Trading Loop)

> Map of key events/commands in the Aurora trading loop.  
> Grounded in `apps/reference/domains/*`, `apps/reference/main.py`, `domain_dict.json` and `EVENTS.md`.

## Key Events and Commands

| Name                            | Type | Emitted by                                                | Consumed by                                                                                       | Schema / Payload (key fields) | Notes / Invariants |
|---------------------------------|------|-----------------------------------------------------------|---------------------------------------------------------------------------------------------------|-------------------------------|--------------------|
| `EVT:MARKET_TICK_RECEIVED`      | EVT  | `MarketDataConnector` (`market_data_connector.py::_emit_market_tick`) | `FeatureEngineering` (`feature_engineering.py::on_market_tick`), optionally `PositionTracking` for mark prices | `schemas/market_tick_received_v1.json` – `ts`, `symbol`, `price`, `bid/ask`, `bid_size/ask_size`, `buy_volume/sell_volume` | Drives every feature update; required fields checked before emit (fail‑closed). |
| `EVT:FEATURES_CALCULATED`       | EVT  | `FeatureEngineering` (`feature_engineering.py::_calculate_features`) | `RiskManagement.on_features_calculated`, `DecisionMaking.on_features`, `RegimeDetector`, downstream monitoring | `feature_engineering/schemas/features_calculated_v1.json` – `ts`, `symbol`, `features{…}` | Features carry Phase1+V2 metrics; TTL enforced in DecisionMaking via `features_ready`. |
| `EVT:RISK_ASSESSMENT_COMPLETED` | EVT  | `RiskManagement.on_features_calculated`                   | `DecisionMaking.on_risk_assessment`                                                               | `risk_management/schemas/risk_assessment_v1.json` – `symbol`, `ts`, `risk_parameters{risk_score,is_trading_allowed,…}` | Includes `is_trading_allowed` and risk budgets; daily gates applied in `daily_gate.py`. |
| `EVT:PORTFOLIO_STATE_UPDATED`   | EVT  | `PositionTracking` (`position_tracking.py::emit_portfolio_state`) | `DecisionMaking.on_portfolio`, `RiskManagement.on_portfolio_state_updated`, `ExecPosFSM._on_portfolio_state_updated`, AuroraBridge | `position_tracking/schemas/portfolio_state_v1.json` – equity, free/cross balances, open_positions_usd, positions[], positions_last_ts_ms | SSOT for portfolio; ExposureGuard relies on `open_positions_usd`, `positions_by_side`, `positions_last_ts_ms` freshness. |
| `EVT:REGIME_DETECTED`           | EVT  | `RegimeDetector` (`regime_detector.py::emit_regime`)      | `DecisionMaking.on_regime`, `feature_engineering` (for regime mapping), MR strategies            | `regime_detector/schemas/regime_detected_v1.json` – `symbol`, `regime`, `confidence`, `warmup{full_ready,…}` | Per‑symbol regime; DecisionMaking blocks trades when `warmup.full_ready=false` for symbol. |
| `EVT:EXPOSURE_SUMMARY_UPDATED`  | EVT  | `ExecPosFSM` + `ExposureGuard` (`fsm.py::_on_portfolio_state_updated` / `_on_order_fill` / `_handle_cancel_event`) | `DecisionMaking.update_exposure_cache`, monitoring                                              | In‑code payload (`exposure_guard.get_exposure_summary()` + portfolio/ fill context) | Summary of exposure by side/symbol; must be consistent with `portfolio_state` and ExposureGuard internal state. |
| `EVT:TRADE_INTENT_PROPOSED`     | EVT  | `DecisionMaking._make_decision_for_symbol`                | AuroraBridge (`apps/reference/main.py::on_trade_intent_proposed`), tests, monitoring             | `decision_making/schemas/trade_intent_v1.json` – intent, size, risk_budget, TCA, why[] | Emitted only after all gates in DecisionMaking pass; carries full XAI why‑chain. |
| `EVT:INTENT_DEFERRED`           | EVT  | AuroraBridge (`AuroraBridge.on_trade_intent_proposed` and QoS handlers) | DecisionMaking (metrics), logs                                                                    | `schemas/intent_deferred_v1.json` – v1: `retry_key`, `next_allowed_ts`, `original_event`, `attempt/max_attempts`, `reason`, `why_chain` | Additive contract: legacy payloads are temporarily accepted, but reliable retry/idempotency is guaranteed only for v1. |
| `EVT:INTENT_DROPPED`            | EVT  | AuroraBridge (stale portfolio / retries exhausted)        | Monitoring only                                                                                   | `{reason, symbol, idempotent_key}` | Intent permanently dropped; must not reach execution. |
| `CMD:OPEN`                      | CMD  | AuroraBridge (`_dispatch_open`), orchestrator FSM         | `ExecPosFSM` (`fsm.py::handle_cmd_open` → `OpenFlowFSM.handle`)                                   | Message payload: `symbol`, `side`, `qty`, `order_type`, `tif`, TP/SL hints, `idempotent_key` | Only MARKET entries allowed (bridge rejects LIMIT); ExecPos applies min_notional, steps, cooldown, ExposureGuard. |
| `CMD:CLOSE`                     | CMD  | DecisionMaking (`ROIExitStrategy`), manual operators      | `CloseFlowFSM.handle`                                                                             | `{symbol, reason, roi,target_roi, reduce_only}` (see `docs/decision_making/docs/EVENTS.md`) | Close flow respects reduce_only and only acts for open positions. |
| `EVT:TRADE_EXECUTED` / `EVT:ORDER_FILL` | EVT | Execution adapters / ExecPos FSM                         | `PositionTracking.on_trade_executed`, `CloseFlowFSM`, monitoring                                 | Exchange fill payload + FSM metadata (symbol, qty, side, price, ids) | PositionTracking updates positions and realized PnL, then emits portfolio update. |

### Invariants

- **Portfolio/Exposure coherence:** `EVT:EXPOSURE_SUMMARY_UPDATED` must reflect the same positions as latest `EVT:PORTFOLIO_STATE_UPDATED`; ExposureGuard treats stale/missing portfolio as **fail‑closed**.
- **Idempotency:** `CMD:OPEN` carries `idempotent_key` where available; `OpenFlowFSM` uses `idempotency_window_sec` from `domains.execution_position.fsm_open` to avoid duplicate opens.
- **QoS vs. Risk:** QoS gates (rate limit, cooldown) in DecisionMaking and AuroraBridge **never bypass** `is_trading_allowed`; trading is blocked if risk gates say “no”, even if QoS would allow.

## Gate Flow Summary

High‑level gate order from features to execution:

1. **Data readiness** – DecisionMaking waits for:
   - fresh `EVT:FEATURES_CALCULATED` (`features_ready` via TTL in `decision_making.py::_features_ready`);
   - matching `EVT:RISK_ASSESSMENT_COMPLETED` (risk parameters present);
   - latest `EVT:PORTFOLIO_STATE_UPDATED` (cached in `DecisionMaking.latest_portfolio`).
2. **Regime and per‑symbol constraints** – per‑symbol regime cache from `EVT:REGIME_DETECTED` and aurora instrument config (`allowed_regimes`, MR overrides).
3. **Risk gates** – `DailyRiskState` (daily loss / drawdown, session CVaR) and risk score thresholds (`domains.risk_management.*`).
4. **QoS gates** – symbol cooldown and rate limits (`domains.decision_making.qos` + `trading.decision.qos`), both in DecisionMaking and AuroraBridge.
5. **Exposure gates** – ExposureGuard hard/soft limits (`domains.execution_position.exposure_guard`, `trading.execution.exposure`, `trading.risk.soft_limits`).
6. **Execution FSM guards** – instrument specs (min_notional, tick/step size), brackets, orphan cleanup (`OpenFlowFSM`, `ManageFlowFSM`, `OrderGuardian`).

These gates together ensure a **fail‑closed** pipeline: missing or stale inputs, misconfigured thresholds, or stale portfolio/exposure states result in deferrals or blocks, not “best‑effort” trades.
