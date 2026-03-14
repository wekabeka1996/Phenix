# JOURNAL_мій

## 2026-03-14

### EP-CONTRACT-BOUNDARY — Очищення контрактних меж execution_position
- **3 co-emitter gaps вирішено:**
  - `EVT:EXPOSURE_SUMMARY_UPDATED`: власник змінено з risk_management на execution_position (EP — єдиний емітер + власник схеми).
  - `EVT:TRADE_INTENT_REJECTED`: валідна ко-емісія, додано `co_emitters: [execution_position]`.
  - `EVT:TRADE_EXECUTED`: валідна ко-емісія, додано `co_emitters: [adapters, execution_position]`.
- **NRR залежність:** `leverage_service.py` мігровано з прямого імпорту з decision_making на `shared/types.py`. Нуль прямих DM імпортів залишилось в EP.
- **8 guardrail тестів** в `test_ep_contract_boundary_guardrails.py`: ownership (2), co_emitters (2), NRR boundary (2), domain_dict notes (2).
- Звіт: `reports/domains/EXECUTION_POSITION_CONTRACT_BOUNDARY_2026-03-14.md`

### EP-DOMAIN-AUDIT — Аудит та структурний хардінг домену execution_position
- **Фаза A (Context Map):** 40 live .py файлів, ~16,500 LOC, 11 JSON схем, 11 doc файлів. 9 подій споживається, 31 емітується. ~1,192 тестових функцій у 147 файлах.
- **Стан ownership:** OrderIndex = SSOT для ордерів, ManageFlowFSM = SSOT для позицій, ExposureGuard/ExposureManager = exposure state.
- **Ключова знахідка:** 3 окремі OrderStatus enum-и (domain/wire/persistence) — навмисне шаруватість, не мерджити.
- **Очищення:** 3 ghost subpackages видалено (aggregator_oco, observability, shadow_execpos — ~38 ghost .pyc). 12 ghost .pyc в root/infra __pycache__. Виправлено зламаний `tests/domains/conftest.py` (видалено `adapter_live` fixture з посиланням на `binance_execution_adapter`).
- **Документація:** Створено авторитетний `execution_position/README.md` (state ownership map, FSM architecture, 31 events, forbidden patterns). Створено `domain_dict.json` v1.0.0 (9 imports, 31 exports, 19 components, ssot_notes). Оновлено `docs/ATLAS.md` та `docs/README.md` (staleness notes).
- **13 guardrail тестів** в `test_ep_domain_structural_guardrails.py`: pycache ghosts (2), ghost subpackages (1), deleted module imports (1), domain_dict consistency (3), triple OrderStatus layered (4), reasons completeness (1), empty tests (1).
- **3 co-emitter gaps:** EP емітує EVT:TRADE_INTENT_REJECTED, EVT:EXPOSURE_SUMMARY_UPDATED, EVT:TRADE_EXECUTED але registry owner — інші домени.
- Оцінка: **8/10** (було ~5/10). Звіт: `reports/domains/EXECUTION_POSITION_DOMAIN_AUDIT_2026-03-14.md`

### DM-DOMAIN-AUDIT — Аудит та структурний хардінг домену decision_making
- **Фаза A (Context Map):** 37 live .py файлів, ~98 тестових файлів, 13 подій споживається, 12 емітується. Всі DM-owned події зареєстровані в `verb_registry_v1.yaml`.
- 9 файлів імпортують з `vfoundation/`, 3 крос-доменні імпорти, 4 production файли імпортують з decision_making зовні.
- **SSOT вирівнювання:** WhyCode = re-export (ALIGNED), NRR = canonical (ALIGNED), події = registered (ALIGNED).
- **Рішення:** Повна реорганізація директорій (logic/, services/, fsm/) **НЕ** виправдана — ~98 тестових файлів зламаються. Стратегія: "виправити гниль, не пересувати меблі".
- **Очищення:** 5 stale __pycache__ ghosts видалено (aurora_scoring_kernel, contracts, portfolio_provider, scoring_direction_strength_v1, signal_score_v2). 1 порожній тест-файл видалено.
- **Документація:** Створено авторитетний `decision_making/README.md`. Оновлено `domain_dict.json` v2.0.0 (13 imports, 12 exports, ssot_notes). Оновлено `__init__.py` v2.0.0. Виправлено `docs/ATLAS.md` та `docs/README.md` (видалено посилання на видалені файли).
- **8 guardrail тестів** в `tests/domains/decision_making/test_dm_domain_structural_guardrails.py`: pycache ghosts, WhyCode re-export identity, no deleted module imports, domain_dict consistency (3 тести), no empty test files.
- Оцінка: **8/10** структурна чіткість (було ~5/10 до очищення).
- Звіт: `reports/domains/dm_domain_audit_2026-03-14.md`

### CONTRACT-SSOT-CONSOLIDATION — Консолідація єдиного джерела істини контрактного шару
- Визначена канонічна архітектура: `verb_registry_v1.yaml` = CANONICAL реєстр, `vfoundation/core/why_codes.py` = CANONICAL WhyCode (72 члени), `NormalizedRejectReasons` = CANONICAL NRR.
- **WhyCode форк вирішений:** 7 кодів (SIZING_*, SIGNAL_NEUTRAL) промоутовано з decision_making в vfoundation. `decision_making/why_codes.py` замінено на тонкий re-export.
- NRR-коди в WhyCode позначені DEPRECATED (семантичний дрифт vs канонічний NRR).
- `format_why_with_details` уніфіковано до variadic сигнатури `*details: str`.
- **12 мертвих записів реєстру** позначено `status: deprecated` (DEC:CANCEL, EVT:EXPIRED, EVT:FILL, EVT:MARKET_TICK_FORWARDED, EVT:MR_SIGNAL_PRODUCED, EVT:NEOCORTEX_STATE_UPDATED, EVT:ORCHESTRATOR_ERROR, EVT:ORDER_EXECUTED, EVT:PARTIAL_FILL, EVT:REJECTED, EVT:TICK_RECEIVED, EVT:VERB).
- **VERB_PAYLOAD_MAP** заморожений як COMPATIBILITY-ONLY (11 записів, не використовується в production).
- Створено архітектурну специфікацію: `docs/contracts/CONTRACT_ARCHITECTURE.md`.
- 9 guardrail тестів в `tests/contracts/test_contract_ssot_guardrails.py`.
- 327 тестів пройдено, 0 не пройшло (contracts, WhyCode, NRR, config SSOT).
- Звіт: `reports/contracts/CONTRACT_SSOT_CONSOLIDATION_2026-03-14.md`

### CONTRACT-AUDIT — Аудит словника подій та реєстру схем
- Повний аудит контрактного шару: 88 контрактів в коді, 68 записів в реєстрі, 40 JSON схем.
- Знайдено 20 контрактів які емітяться в рантаймі але відсутні в реєстрі — всі додані.
- Зламане посилання на схему ORDER_ACK виправлено (невірний шлях).
- Видалено дублікат PROCESS_STRATEGY_BLOCKED.
- 6 записів з `owner: unknown` отримали коректного власника на основі коду.
- ANCHOR_UPDATED виправлений: власник був `decision_making`, реально емітить `market_data`.
- 12 мертвих/legacy записів виявлено (EVT:EXPIRED, EVT:FILL, EVT:MARKET_TICK_FORWARDED та інші) — рекомендовано позначити DEPRECATED.
- 8 сирітських JSON схем (файли є але реєстр не посилається).
- WhyCode enum роздвоєний між vfoundation та decision_making — потребує рішення.
- 28 нових регресійних тестів в `tests/contracts/test_contract_registry_audit.py`.
- Звіт: `reports/contracts/CONTRACT_AUDIT_2026-03-14.md`

### CONFIG-NAMESPACE-CLEANUP
- Дослідження показало що `config/aurora_baseline/` та `config/mean_reversion/` — мертві директорії, створені агентами. Нуль посилань в коді, тестах, CI.
- `config/aurora_baseline/` — заморожений snapshot до Phase 9 (backtest mode, всі символи на aurora, шаблонні ваги).
- `config/mean_reversion/` — ізольований backtest-профіль для MR стратегії (тільки DOGE + 1000PEPE).
- Обидві переміщені в `archive/config_snapshots/` зі створенням маніфесту.
- `config/README.md` — новий SSOT контракт: `config/aurora/` єдина канонічна runtime директорія.
- `PROJECT_ATLAS.md` очищений від 20+ мертвих записів.
- Регресійний тест додано: `tests/config/test_config_namespace_ssot.py`.

## 2026-03-13

### MEAN_REVERSION_STATE_MACHINE_PASSPORT re-audit
- Re-audited `config/docs/mean_reversion_state_machine_passport.md` against current MR YAML, typed config, registry assignment, `MeanReversion1mStrategy`, `MeanReversionHandler`, plugin wiring, and focused tests.
- Confirmed the main architecture split:
  - `MeanReversion1mStrategy.on_bar()` owns state-machine math and signal formation
  - `MeanReversionHandler` owns activation, payload validation, liquidity gate, objective overlay, and emission
  - `ExecPosFSM` / `ManageFlowFSM` own downstream execution/reconciliation, not the MR state machine
- Corrected current live runtime facts:
  - live timeframe is `300s`, despite stale `1m` / `3m` naming in parts of code/comments
  - current live assigned MR symbol is `DOGEUSDT`
- Logged drift:
  - old event-contract integration test is skipped and still tied to obsolete tick-path assumptions
  - naming drift in MR code/comments can mislead docs if copied literally
- Created missing audit artifact:
  - `reports/docs_audit/mean_reversion_state_machine_passport_audit_report.md`
- Refreshed main passport:
  - `config/docs/mean_reversion_state_machine_passport.md`

### MD_AMR_STRATEGY_PASSPORT re-audit
- Re-audited `config/docs/md_amr_strategy_passport.md` against current profile YAML, strategy registry assignment, plugin startup, md_amr handler runtime, gateway validation, and focused tests.
- Confirmed that `md_amr` is a normal in-process handler path via `MDAMRPlugin -> MDAMRHandler`, not a sentinel or bridge strategy.
- Corrected live activation semantics:
  - runtime symbols are assignment-first (`XRPUSDT`, `BNBUSDT` currently)
  - unassigned asset blocks in `md_amr.yaml` remain dormant profile entries
  - assigned symbols fail closed if `exit` or `allowed_regimes` are missing
- Logged runtime drift:
  - `gtx_fallback_to_market` currently logs fallback intent but no real fallback path was traced in the handler
  - `reconcile_position()` exists and uses `drift_tolerance`, but no external caller was found in the audited live path
- Created missing audit artifact:
  - `reports/docs_audit/md_amr_strategy_passport_audit_report.md`
- Refreshed main passport:
  - `config/docs/md_amr_strategy_passport.md`

### LLM_MICROSTRUCTURE_STRATEGY_PASSPORT re-audit
- Re-audited config/docs/llm_microstructure_strategy_passport.md against current profile YAML, registry contract, sentinel plugin, shadow telemetry ingress, bridge mapper, downstream safety gates, and tests.
- Confirmed the main architecture correction: this is an external-intent bridge strategy, not a normal in-process strategy handler.
- Logged key drift:
  - profile `timeframe_sec=60`, but bridge currently emits `tf_sec=300`
  - `llm_microstructure.enabled` is typed, but no direct runtime consumer was found for hard disable semantics
  - runtime authority is split across profile config and `trading.llm_orchestration`
- Created missing audit artifact:
  - reports/docs_audit/llm_microstructure_strategy_passport_audit_report.md
- Refreshed main passport:
  - config/docs/llm_microstructure_strategy_passport.md

### INSTRUMENTS_PASSPORT re-audit
- Re-audited `config/docs/instruments_passport.md` against current `instruments.yaml`, typed contracts, loader wiring, execution-position runtime, decision-making sizing, startup filter validation, and tests.
- Corrected the identity model: canonical symbol registry is driven mainly by `config.instruments` map keys, not nested `symbol`.
- Confirmed active runtime ownership for:
  - precision and min-constraint fields
  - execution leverage/margin policy
  - sizing margin budget
  - per-symbol flip contract
- Logged important drift:
  - `execution.max_notional_utilization` typed/live-validated but no runtime consumer found
  - strategy-side leverage is now secondary to instruments SSOT and mismatches are only warned as legacy drift
- Created missing audit artifact:
  - `reports/docs_audit/instruments_passport_audit_report.md`
- Refreshed main passport:
  - `config/docs/instruments_passport.md`

### STRATEGIES_PASSPORT re-audit
- Re-audited `config/docs/strategies_passport.md` against current registry YAML, strategy profiles, config loader, StrategyRuntime, arbitration logic, and strategy handlers.
- Confirmed that strategy activation is assignment-first via `strategies_registry.assignments`.
- Corrected the old loose model: assigned strategy IDs drive both profile loading and plugin startup.
- Logged strategy-specific drift:
  - `arbitration.logging.log_level` typed but unused
  - `aurora.enabled` is not the hard activation SSOT
  - `llm_microstructure` is sentinel/bridge-driven, not a normal in-process handler
- Created missing audit artifact:
  - `reports/docs_audit/strategies_passport_audit_report.md`
- Refreshed main passport:
  - `config/docs/strategies_passport.md`

### AURORA_MATH_PASSPORT re-audit
- Re-audited `config/docs/aurora_math_passport.md` against current Aurora YAML, Pydantic, runtime mixins/kernels, rollout contract, and math tests.
- Corrected the consumer map: current math path is split across `aurora_handler.py`, `aurora_config_loader.py`, `aurora_scoring_helpers.py`, `aurora_decision.py`, `aurora_scoring_kernel.py`, and `quadratic_scoring_kernel.py`.
- Corrected production normalization semantics: strict config boundary is `signed_v2` only.
- Confirmed current live Aurora math remains linear `v2`; Quadratic stays optional and not activated by current YAML.
- Logged math-specific drift:
  - `decision.regime_thresholds` not used in live Aurora threshold math
  - `AuroraInstrumentConfig.scoring_version` not consumed by loader
  - per-symbol `neutral_threshold` probed by runtime but absent from strict typed config
  - `liquidity_gate.failsafe_qty_check` diagnostic only
- Created / refreshed artifacts:
  - `config/docs/aurora_math_passport.md`
  - `reports/docs_audit/aurora_math_passport_audit_report.md`

### SCORING_PASSPORT re-audit
- Re-audited `config/docs/scoring_passport.md` against current YAML, Pydantic, runtime, schemas, and tests.
- Corrected the main false narrative: Quadratic exists in code, but active Aurora live scoring is still `v2`.
- Confirmed that symbol ownership comes from `config/aurora/strategies.yaml`, not from `aurora.assets`.
- Logged declared-but-unused fields found during trace:
  - `strategies.aurora.decision.regime_thresholds`
  - `scoring_engine.exposure_cap`
  - `scoring_engine.min_pillar_confidence`
  - `liquidity_gate.failsafe_qty_check`
  - `trading.risk.daily.max_realized_loss_usd`
- Created / refreshed artifacts:
  - `config/docs/scoring_passport.md`
  - `reports/docs_audit/scoring_passport_audit_report.md`
- Follow-up is required at runtime-contract level; no business-logic code was changed in this task.

### MEAN REVERSION INCIDENT FORENSIC RESEARCH (COMPLETED)
- **Scope**: Full evidence gathering and analysis of the recent `mean_reversion` incident on DOGEUSDT.
- **Investigated**: 5 intents, 3 entries, zero execution FSM syncs.
- **Proven**:
  1. Strategy entered strictly according to code (`min_bb_width` > 0.005 passed).
  2. Quant logic failed by fading a severe volatility squeeze breakout (`bb_width` ~ 0.8%).
  3. Brackets (`STOP_MARKET`) were properly dispatched to Binance Testnet.
  4. Binance Testnet closed the position (proven by `Positions: 0` polling), but `ManageFlowFSM` failed to reconcile the websocket `ORDER_UPDATED` event, causing split-brain.
  5. The split brain allowed a new pyramided order to overwrite the internal FSM state, sending the first order to the `TTL_EXPIRED_3600s` garbage collector.
- **Next Actions Recommended**: Review `ExecPosFSM` concurrency lock for dictionary overwrites, check BinanceAdapter's websocket parsing for `STOP_MARKET` updates, and increase `min_bb_width` for DOGEUSDT to > 0.015.

### RUNTIME FORENSIC AUDIT (COMPLETED)
- **Scope**: Deep forensic audit to answer 4 runtime questions regarding md_amr cold start, Aurora inactivity, Quadratic logging, and FE integrity.
- **Investigated**: Runtime artifacts including aurora_core.log, aurora_trades.log, event_chain.log, and domain_decision_making.log.
- **Proven**:
  1. `md_amr` cold start is strictly blocked by a 96-bar (24h) internal counter. Can be fixed via offline hydration.
  2. `Aurora` (e.g. DOGEUSDT) successfully evaluates features and outputs intents but gets blocked by `ExposureGuard` due to a `local_manage_state_conflict` (bug: both states are FLAT).
  3. Feature Engineering is missing all basic TA indicators (`bb_position`, `rsi_14`, etc.), completely breaking `ta_ensemble`.
  4. Quadratic logging (`pillar_sum`) is calculated in FE but vanishes in Decision Making; it is completely unobservable for operators.
- **Next Actions Recommended**: Fix `ExposureGuard` FLAT/FLAT conflict, restore TA indicators in FE, hydrate md_amr on startup, and add `pillar_sum` to Decision logs.
