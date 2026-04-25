# 📄 Semantic Configuration Passport: `config/aurora/strategies.yaml` (Full File)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/strategies_passport_gemini_v1.md
> - Scope: Lines 1-100 (Full File) of `config/aurora/strategies.yaml`
> - Purpose: Capability mapping for strategy-to-symbol assignments and multi-strategy arbitration.

Цей паспорт є **єдиним джерелом правди (SSOT)** для того, які алгоритмічні стратегії дозволено запускати на яких активах, та як система вирішує конфлікти, якщо кілька стратегій генерують сигнали одночасно.

---

## 1. Strategy Assignments (`assignments`)

- **Capability:** Маршрутизатор (Router) рівня активів. Визначає, який набір стратегій слухає фічі та приймає рішення для конкретного символу.
- **Sensitivity:** 
  - Якщо символ відсутній у цьому списку, система **не буде** торгувати ним взагалі, навіть якщо підписана на його біржові сокети.
  - На один актив можна призначити кілька стратегій (наприклад, `aurora` та `md_amr` для XRPUSDT).
- **Поточний Стан (Причинність):**
  - `ETHUSDT`, `SOLUSDT`, `BTCUSDT`, `BNBUSDT`: Керуються виключно базовою стратегією `aurora` (Bar-driven multi-signal strategy).
  - `XRPUSDT`: Гібридний режим (`aurora` + `md_amr` як фолбек).
  - `1000PEPEUSDT`: Виділено виключно під ШІ/LLM-пісочницю (`llm_microstructure`).
  - *DOGEUSDT*: Закоментовано (тимчасово відключено від торгівлі оператором).

---

## 2. Arbitration (Конфліктологія) (`arbitration`)

Коли на одному символі (напр., XRPUSDT) працюють дві стратегії одночасно, вони можуть згенерувати конфліктні `TradeIntent` в одну й ту саму мілісекунду. Блок `arbitration` розв'язує такі колізії.

### `arbitration.mode`
- **Type:** `string` (enum: `priority`).
- **Capability:** Визначає механізм вирішення спорів. Наразі підтримується лише `priority` (ранжування за жорсткою ієрархією). Режими `regime` (хто сильніший у поточному тренді) та `round_robin` зарезервовані, але ще не імплементовані.

### `arbitration.window_ms`
- **Type:** `int` (1000).
- **Capability:** Часове "Вікно Дедуплікації та Конфлікту" (Decision Window). 
- **Причинність:** Якщо `aurora` та `mean_reversion` генерують наміри з різницею більше ніж `1000 ms`, вони розглядаються як незалежні дії. Якщо ж різниця $< 1000 ms$, активується Арбітр і "виживає" лише одна стратегія. Це запобігає ситуації, коли швидка стратегія назавжди "задушить" (suppress) повільну гілку на гібридних символах.

### `arbitration.priority`
- **Type:** `dict` (Мапа рангів).
- **Capability:** Жорстка ієрархія стратегій (менше значення = вищий пріоритет).
- **Sensitivity:** 
  1. `aurora: 1` (Абсолютний пріоритет).
  2. `mean_reversion: 2`.
  3. `md_amr: 3`.
  4. `llm_microstructure: 4` (ШІ має найнижчий пріоритет. Якщо базова стратегія FSM і ШІ генерують сигнал одночасно, ШІ завжди програє. Це ще один ешелон **Bounded Control**).

### `arbitration.logging`
- **Capability:** Форматує запис про відхилений (переможений) інтент.
- `rejected_why_prefix: "ARBITRATION_REJECT"` гарантує, що в логах (`trade_lifecycle.jsonl`) та `shadow_journal` ми зможемо чітко відрізнити інтенти, які були відхилені через Risk Gates, від інтентів, які просто програли конкуренцію іншій стратегії.