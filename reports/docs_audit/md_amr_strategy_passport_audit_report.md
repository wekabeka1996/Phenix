# Audit Report: `config/docs/md_amr_strategy_passport.md`

Дата: 2026-03-13
Статус: completed
Формат: code-trace re-audit against current config, typed contracts, runtime handler, gateway, startup wiring, and focused tests

## Scope

Переаудитовано:
- `config/aurora/strategies/md_amr.yaml`
- `config/aurora/strategies.yaml`
- `apps/reference/config_models.py`
- `apps/reference/main.py`
- `apps/reference/domains/strategies/plugins/md_amr.py`
- `apps/reference/domains/decision_making/md_amr_handler.py`
- `apps/reference/domains/decision_making/strategy_gateway.py`
- `tests/domains/decision_making/test_md_amr_strategy_gateway.py`
- `tests/domains/decision_making/test_md_amr_runtime_readiness.py`

## Confirmed

- `md_amr` є звичайною in-process strategy через `MDAMRPlugin -> MDAMRHandler`, а не sentinel/bridge path.
- Live activation визначається assignment-first через `config/aurora/strategies.yaml`; поточні assigned symbols: `XRPUSDT`, `BNBUSDT`.
- Handler fail-closed перевіряє для assigned symbols: profile presence, `enabled=true`, asset block presence, непорожній `allowed_regimes`, наявність `exit`.
- `llm_gate` реально споживається через `features.sentiment_state` і ставить тимчасовий macro block.
- `concentration_guard` реально працює як defer gate на надлишкові entry в одному bar timestamp.
- `objective` реально інтегрований у entry path і працює fail-closed при відсутності required data, коли domain config strict.
- `StrategyGateway` вимагає повний md_amr trace і окремо підтримує reduce-only paths для `FULL_CLOSE` та `PARTIAL_CLOSE`.
- Runtime readiness test підтверджує live bars gate `BARS_REQUIRED_COLD_START`.

## Corrected

- Старий паспорт описував усі asset blocks YAML так, ніби вони однаково live-active. Насправді runtime активує лише перетин assignment symbols і enabled asset blocks.
- Старий паспорт не відображав, що без `exit` та `allowed_regimes` assigned symbol не проходить live startup contract.
- Опис execution path був надто сильним щодо `gtx_fallback_to_market`: у traced handler path підтверджено лише bookkeeping/logging, а не реальний market fallback.
- Опис `reconciliation` як повністю активного runtime path був завищеним: локальна reconcile-функція є, але зовнішній виклик у traced live path не знайдено.

## Drift Ledger

- `gtx_fallback_to_market` за назвою обіцяє сильнішу поведінку, ніж підтверджує audited handler path.
- `reconciliation.enabled` / `drift_tolerance` мають локального consumer-а, але end-to-end wiring не простежено.
- У профілі зберігаються asset blocks для неassigned symbols; це профільні заготовки, а не автоматично live-active universe.

## Final Verdict

`config/docs/md_amr_strategy_passport.md` повністю переписано під поточний code-driven стан. Новий паспорт більше не трактує YAML як самодостатню правду і чітко відділяє:
- assignment SSOT
- strategy-profile SSOT
- підтверджену handler/gateway runtime behavior
- декларативні поля, чий end-to-end ефект зараз слабший або не повністю доведений
