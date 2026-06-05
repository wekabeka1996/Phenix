# PnL Forensics Checklist

## Фаза 0 — Попередній підрахунок
- [ ] Запущено `tools/forensics/wal_intent_summary.py` — загальний підрахунок PROPOSED/REJECTED
- [ ] Запущено `tools/monitoring/extract_equity_free_usdt.py` — зафіксовано поточний баланс
- [ ] Загальна кількість ORDER_INTENT по фазах задокументована

## Фаза 1 — Кількісний аудит ORDER_INTENT
- [ ] Підрахунок ORDER_INTENT по source_fsm виконано автоматизовано (не вручну)
- [ ] Кількість DECISION_INTENT_REJECTED по NRR-кодах зафіксована
- [ ] Кількість ордерів, що не активували позицію, встановлена

## Фаза 2 — Аналіз позицій
- [ ] Запущено `tools/forensics/entry_execution_report.py`
- [ ] Запущено `tools/forensics/entry_fill_audit.py`
- [ ] Кожна позиція класифікована: ACTIVATED / REJECTED / ORPHANED

## Фаза 3 — Класифікація close_reason
- [ ] Кожна activated позиція має визначений close_reason
- [ ] Розподіл close_reason: TP / SL / TTL / NRR / VALIDATION_FAIL / DISAPPEARANCE

## Фаза 4 — Feature engineering cross-reference
- [ ] Для кожної позиції знайдено features snapshot при відкритті
- [ ] Для кожної позиції знайдено features snapshot при закритті (якщо доступне)
- [ ] Запущено `tools/forensics/deep_wal_forensics.py`
- [ ] Відповідність features та рішення системи оцінена

## Фаза 5 — PnL розрахунок
- [ ] PnL_gross і PnL_net розраховані для кожної closed позиції
- [ ] PnL агрегований по символу, close_reason та режиму
- [ ] Запущено `tools/backtest/backtest_summarize.py` (якщо доступні backtest дані)

## Фаза 6 — Sidecar та Policy
- [ ] Запущено `tools/forensics/position_policy_sidecar_validation.py`
- [ ] SUPPRESSED події підраховані та класифіковані
- [ ] evaluation_mode зафіксований

## Фаза 7 — Gate аналіз
- [ ] Запущено `tools/forensics/gate_effect_report.py`
- [ ] Перевірено rv_bps vs cost_bps для заблокованих трейдів

## Фаза 8 — Хронологічна реконструкція
- [ ] UTC-таймлайн побудований для кожного досліджуваного rid
- [ ] Всі 8 фаз події (intent → fill → close → features) задокументовані

## Фінальна перевірка
- [ ] Всі твердження позначені: ФАКТ / ВИСНОВОК / НЕПІДТВЕРДЖЕНО
- [ ] Звіт складений українською мовою
- [ ] Первинна причина збитку ідентифікована з доказовою базою
- [ ] Рекомендації сформульовані та прив'язані до конкретних інструментів/конфігів
