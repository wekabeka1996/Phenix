# Аналіз Qty Rejection для всіх монет

## Проблема

Після TASK50 (Quantity Normalization Contract) система відхиляє ордери, де qty rounded to zero.

## Поточні налаштування

- **Equity**: $677.50
- **Percent equity**: 5% = $33.87 position size
- **Rounding**: ROUND_DOWN до step_size

## Аналіз по монетах

### ❌ BTCUSDT - FAIL
- **Price**: $89,104
- **Step size**: 0.001
- **Min qty**: 0.001
- **Raw qty**: 0.00038
- **Rounded qty**: 0.000 → **FAIL**
- **Причина**: step_size = 0.001, але position size занадто малий

### ✅ ETHUSDT - OK
- **Price**: $2,500
- **Step size**: 0.01
- **Min qty**: 0.01
- **Raw qty**: 0.0135
- **Rounded qty**: 0.01 → **OK**
- **Notional**: $25

### ❌ SOLUSDT - FAIL
- **Price**: $150
- **Step size**: 1
- **Min qty**: 1
- **Raw qty**: 0.226
- **Rounded qty**: 0 → **FAIL**
- **Причина**: step_size = 1, min_qty = 1, position size занадто малий

### ✅ DOGEUSDT - OK
- **Price**: $0.20
- **Step size**: 1
- **Min qty**: 1
- **Raw qty**: 169
- **Rounded qty**: 169 → **OK**
- **Notional**: $33.80

### ✅ XRPUSDT - OK
- **Price**: $1.20
- **Step size**: 0.1
- **Min qty**: 0.1
- **Raw qty**: 28.2
- **Rounded qty**: 28.2 → **OK**
- **Notional**: $33.84

## Висновки

### Проблемні монети
- **BTCUSDT**: Потрібно збільшити position sizing
- **SOLUSDT**: Потрібно збільшити position sizing

### Робочі монети
- **ETHUSDT**: OK з поточним sizing
- **DOGEUSDT**: OK з поточним sizing
- **XRPUSDT**: OK з поточним sizing

## Рішення - Оновлені regime_sizing

### Для SOLUSDT:
```yaml
regime_sizing:
  HIGH_VOLATILITY: 5.0      # $169.35 - enough for 1 SOL minimum
  LOW_VOLATILITY: 6.0       # $203.22 - aggressive sizing
  MEAN_REVERSION: 5.0       # $169.35 - balanced
```

### Для BTCUSDT:
```yaml
regime_sizing:
  HIGH_VOLATILITY: 3.0      # $101.61 - enough for BTC minimum
  LOW_VOLATILITY: 4.0       # $135.48 - aggressive sizing
  MEAN_REVERSION: 3.5       # $118.55 - balanced
```

Тепер обидва BTC та SOL працюють у всіх режимах волатильності.</content>
<parameter name="filePath">/home/wekabeka/Музыка/Phenix/ALL_SYMBOLS_QTY_ANALYSIS.md