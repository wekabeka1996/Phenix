# VF-DICT-FORENSIC-04 — Сопоставление с реальным Aurora event-пространством
Дата: 2026-01-08

## Источники
- `apps/reference/domains/**/domain_dict.json`
- `vfoundation/dictionaries/domains/domain_*.yaml`
- Поиск по коду `EVT:|CMD:|DEC:|ASK:|UPD:|ERR:` в `apps/reference` и `vfoundation`

## Сводка количеств
- Токены op:verb из domain_dict + vfoundation domain YAML: 23
- Токены op:verb, найденные в коде (строковые литералы): 53

## Быстрые несоответствия (проверка только OP)
- OP-часть согласована: в коде используются только {ASK,DEC,CMD,EVT,UPD,ERR}.

## Примеры (top 50)
- ASK:CLOSE
- ASK:EVAL
- ASK:OPEN
- CMD:APPLY_MODULATION
- CMD:CLOSE
- CMD:DM_MODULATE
- CMD:OPEN
- DEC:ADJUST
- DEC:CANCEL
- DEC:CANCEL_ORDER
- DEC:CLOSE
- DEC:EVAL
- DEC:OPEN
- DEC:PLACE_ORDER
- DEC:RISK_ASSESSMENT_COMPLETED
- EVT:ACCOUNT_UPDATE_RECEIVED
- EVT:ALPHA_SCORE_CALCULATED
- EVT:ANCHOR_UPDATED
- EVT:BALANCE_UPDATE_RECEIVED
- EVT:CANCELLED
- EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE
- EVT:DECISION_BLOCKED
- EVT:DECISION_TRACE_EMITTED
- EVT:EXPOSURE_SUMMARY_UPDATED
- EVT:FEATURES_CALCULATED
- EVT:FILL
- EVT:FUNDING_UPDATE
- EVT:INTENT_DEFERRED
- EVT:INTENT_DROPPED
- EVT:MARKET_TICK_FORWARDED
- EVT:MARKET_TICK_RECEIVED
- EVT:NEOCORTEX_TRADE_INTENT_PROPOSED
- EVT:OI_UPDATE
- EVT:ORCHESTRATOR_ERROR
- EVT:ORDER_ACK
- EVT:ORDER_EXECUTED
- EVT:ORDER_FILL
- EVT:ORDER_PLACED
- EVT:ORDER_REJECTED
- EVT:ORDER_STATE_CHANGED
- EVT:ORDER_TIMEOUT
- EVT:PARTIAL_FILL
- EVT:PORTFOLIO_STATE_UPDATED
- EVT:POSITION_CLOSED
- EVT:REGIME_DETECTED
- EVT:RISK_ASSESSMENT_COMPLETED
- EVT:STRATEGY_DECISION_BLOCKED
- EVT:STRATEGY_SIGNAL_PRODUCED
- EVT:SYMBOL_TIDY
- EVT:TRADE_EXECUTED

## Что я доказал фактами
- Реальный event-space в Aurora представлен строковыми токенами `OP:VERB` в доменных dict-артефактах и в коде.
- Глобальный словарь v2.2 сейчас не содержит реестр всех VERB, поэтому строгая проверка verb по global_v2_2.yaml невозможна без расширения формата/доп. источников.

## Что осталось неизвестным
- Полный список VERB в рантайме лучше извлекать из реестра handler-регистраций Router (если он есть централизованно) — это будет в отдельном шаге, если нужно.
