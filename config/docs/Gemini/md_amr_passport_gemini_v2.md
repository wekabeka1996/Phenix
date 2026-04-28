# 📄 Semantic Configuration Passport: `config/aurora/strategies/md_amr.yaml` (Part 2)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/md_amr_passport_gemini_v2.md
> - Scope: Lines 151-473 of `config/aurora/strategies/md_amr.yaml`
> - Purpose: Capability mapping for asset overrides and dynamic exits in the MD-AMR strategy.

Цей паспорт описує завершальну частину налаштувань для стратегії Multi-Dimensional AMR, зосереджуючись на специфічних профілях активів та їхніх динамічних стопах.

---

## 6. Asset-Specific Overrides (`assets`) - Продовження

Стратегія MD-AMR має дуже тонке налаштування для кожного активу. Оскільки ця стратегія ловить аномалії, різні активи поводяться по-різному залежно від режиму.

### `ETHUSDT` (Закінчення блоку)
- **Capability:** Динамічні ліміти виходу (`regime_tpsl`).
- **Sensitivity:** 
  - `min_sl_pct: 0.002` (0.2%) / `max_sl_pct: 0.015` (1.5%). Жорсткі межі розширення стопу для ефіру.
  - `min_tp_rr: 0.3` / `max_tp_rr: 3.5`. Відношення Risk/Reward затиснуте в цих межах.

### `SOLUSDT` (Консервативний режим)
- **Capability:** Увімкнено (`enabled: true`), але суворо обмежено.
- **Sensitivity:** `allowed_regimes: [LOW_VOLATILITY]`. 
  - *Причинність:* На відміну від `aurora` (яка торгує SOL агресивно), стратегія AMR на SOL активується **тільки** у низькій волатильності. Вона шукає короткі простріли каналу, поки ринок "спить".
  - `sl_mult` для `LOW_VOLATILITY` становить `0.65` (дуже короткий стоп), а для шторму `HIGH_VOLATILITY` — `1.3`. Але оскільки шторм заблоковано в `allowed_regimes`, ці множники працюють як fail-safe для перехідних станів.

### `XRPUSDT` (Основний цільовий актив)
- **Capability:** Увімкнено (`enabled: true`). Гібридний симбіоз з `aurora`.
- **Sensitivity:** `allowed_regimes: [MEAN_REVERSION, TREND_DOWN]`. 
  - *Причинність:* XRP часто демонструє сильні контртрендові рухи після падінь (TREND_DOWN) та довгі періоди боковиків. Тому стратегія націлена саме на ці два стани.
  - Стоп-лос ширший: `sl_pct: 0.013` (1.3%) базовий. Це пояснюється "хвостатим" характером XRP, де короткі стопи часто вибиває маніпулятивними сквизами.

### `BTCUSDT`, `DOGEUSDT`, `BNBUSDT`
- **Capability:** Вимкнені (`enabled: false`). 
- **Причинність:** Конфігурації збережені як бекапи (Cold Storage) на випадок зміни ринкових умов або архітектурного рішення про перерозподіл роутингу. Наразі ці активи повністю передані іншим стратегіям (`aurora` або вимкнені зовсім).

---
*Аудит конфігу `md_amr.yaml` завершено.*