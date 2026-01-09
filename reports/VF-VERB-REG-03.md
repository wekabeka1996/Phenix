# VF-VERB-REG-03 — Owner labeling для top-N verb
Дата: 2026-01-08

## Что размечено
- Размечено owner не менее чем для top-20 токенов по частоте (runtime).
- Всего owner!=unknown: **20**

## Топ-20 (по частоте)
- CMD:OPEN (count=32) -> owner=execution_position
- EVT:FEATURES_CALCULATED (count=28) -> owner=feature_engineering
- DEC:CLOSE (count=25) -> owner=execution_position
- EVT:STRATEGY_SIGNAL_PRODUCED (count=20) -> owner=decision_making
- DEC:OPEN (count=19) -> owner=execution_position
- EVT:TRADE_INTENT_PROPOSED (count=19) -> owner=decision_making
- EVT:PORTFOLIO_STATE_UPDATED (count=19) -> owner=position_tracking
- EVT:REGIME_DETECTED (count=17) -> owner=regime_detector
- EVT:ANCHOR_UPDATED (count=13) -> owner=decision_making
- CMD:CLOSE (count=13) -> owner=execution_position
- EVT:MARKET_TICK_RECEIVED (count=12) -> owner=market_data
- EVT:TRADE_EXECUTED (count=11) -> owner=position_tracking
- EVT:RISK_ASSESSMENT_COMPLETED (count=8) -> owner=risk_management
- EVT:SYMBOL_TIDY (count=7) -> owner=market_data
- EVT:ACCOUNT_UPDATE_RECEIVED (count=7) -> owner=account_balance
- EVT:EXPOSURE_SUMMARY_UPDATED (count=7) -> owner=risk_management
- EVT:INTENT_DEFERRED (count=6) -> owner=decision_making
- DEC:ADJUST (count=6) -> owner=execution_position
- EVT:MARKET_TICK_FORWARDED (count=6) -> owner=market_data
- EVT:ORDER_PLACED (count=5) -> owner=execution_position

## Schema заполнение
- Schema заполняется только при точном совпадении имени файла `<verb_lower>_v1.json`.
  Для остальных оставлено `null` (без догадок).
