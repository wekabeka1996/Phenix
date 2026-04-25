# 📄 Semantic Configuration Passport: `config/aurora/strategies/aurora.yaml` (Part 1)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/aurora_passport_gemini_v1.md
> - Scope: Lines 1-100 of `config/aurora/strategies/aurora.yaml`
> - Purpose: Capability mapping for the core multi-signal alpha strategy (execution overrides & objective functions).

Цей паспорт описує базові налаштування найголовнішої торгової стратегії системи (`aurora`). 

---

## 1. Strategy Identity & Execution Overrides

### `type` / `timeframe_sec`
- **Capability:** `bar_driven` (керована свічками). Працює на базі `timeframe_sec: 300` (5 хвилин). Це означає, що стратегія розраховує свій макро-сигнал раз на 5 хвилин, синхронізуючись із закриттям бару.

### `execution`
- **Capability:** Перевизначає (overrides) глобальні налаштування екзекуції (з `system.yaml`/`trading.yaml`) спеціально для цієї стратегії.
- **`entry_order_type: LIMIT` / `entry_tif: GTX`:** 
  - *Причинність:* Встановлює жорстку вимогу — входити в ринок ТІЛЬКИ як Maker (GTX = Post-Only). Стратегії заборонено перетинати спред і платити Taker-комісію.
  - *Sensitivity:* 🔽 Якщо змінити `entry_tif` на `GTC` або `IOC`, стратегія почне бити по ринку, що згенерує великі витрати на `slippage` (проковзування) і `cost`, повністю зламавши бектести.
- **`gtx_retry_max: 0`:** 
  - *Capability:* Якщо лімітний Maker-ордер одразу перетинається зі стаканом (Order would execute immediately), він скасовується без спроб перевиставлення. Це дуже консервативна поведінка (Zero tolerance to immediate execution).

### `safety_gates`
- **`system_stress_policy: attenuate`:**
  - *Capability:* Реакція стратегії на глобальний системний стрес (з `regime.yaml`). Замість повного вимкнення (halt), стратегія `attenuate` (послаблює) свої сигнали.
  - *`stress_attenuation_factor: 0.5`:* Сигнал стратегії зменшується вдвічі під час паніки на ринку, що відповідно зменшує сайзинг (розмір позиції).

---

## 2. Objective Function (`objective`)

Найскладніший математичний блок стратегії. Керує тим, як система оцінює якість свого наміру (`TradeIntent`) в різних ринкових режимах (Regimes), використовуючи компоненти з `Objective Engine`.

### Механіка `regimes`
Стратегія має специфічні налаштування для 5 базових режимів: `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `TREND_UP`, `TREND_DOWN`, `MEAN_REVERSION`.

Для кожного режиму задаються:
1. **`weights`:** Ваги для 6 компонентів нагороди (cost, risk, edge, execution, info, behavior).
   - *Sensitivity (HIGH_VOLATILITY):* Вага `behavior: 1.4` та `risk: 1.5` сильно підвищена. Це змушує стратегію панічно боятися системного стресу і ризику під час шторму.
   - *Sensitivity (TREND_UP):* Вага `edge: 1.5` підвищена. Стратегія агресивно фокусується на максимізації прибутку (Risk/Reward) і менше боїться волатильності (`risk: 1.0`).
2. **`multiplier`:** Математичний згладжувач (Sigmoid / Logistic).
   - `m_min: 0.1` / `m_max: 2.0`. Якщо `Objective Score` (оцінка наміру) позитивна, сигнал стратегії може бути помножений аж на `2.0` (подвійний розмір входу). Якщо скор негативний, вхід зрізається до `0.1` (майже нуль).
3. **`gate`:**
   - `min_objective_score` (напр., `0.1` для трендів, `0.05` для флету). 
   - *Capability:* Hard Gate (Жорсткий бар'єр). Якщо фінальний скор наміру нижче цього порогу, `enforcement_mode: GATE` примусово блокує цей трейд. Стратегії фізично заборонено входити в ринок з негативним математичним очікуванням.