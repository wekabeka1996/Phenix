# Runbook: ETH TREND_DOWN Counterfactual Research

## 1. Preconditions

```powershell
cd C:\Users\wekab\Music\Phenix
python -V
```

Правила:

- не запускати жоден backtest
- не пайпити output в head
- запускати тільки research script нижче

## 2. Точна команда запуску

```powershell
python tools/research/eth_trend_down_counterfactual.py
```

## 3. Де з'являться результати

- markdown report: reports/eth_trend_down_counterfactual.md
- json summary: reports/eth_trend_down_counterfactual_summary.json

Примітка:

- якщо `logs/backtests/order_log_20260312_010242.jsonl` відсутній, script все одно відпрацює
- у такому випадку `intent linkage coverage` у звіті буде `0/N`

## 4. Що скинути назад в чат

Після запуску скинь:

1. повний блок Executive Verdict з reports/eth_trend_down_counterfactual.md
2. таблицю F0..F6 або повністю, або мінімум рядки для cohort = Jan+Feb, March, Q1
3. назву filter-кандидата, який script позначить як best balanced candidate
4. якщо script покаже, що entry-phase filter недостатній, скинь цей висновок дослівно
