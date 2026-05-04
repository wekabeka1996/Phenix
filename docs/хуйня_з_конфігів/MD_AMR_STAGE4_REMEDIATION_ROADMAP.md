# MD-AMR Stage 4: Remediation Roadmap
**Status:** `APPROVED AFTER SCOPE NARROWING`

## Executive Summary
Емпіричний аудит (Stage 3) повністю сфокусував нас на одній гарантовано-деструктивній складовій в архітектурі `MDAMRStrategyV11`: головною і єдиною доведеною проблемою, що безпосередньо блокує здатність стратегії заробляти PnL, є конфлікт всередині `exit semantics` (Killswitch vs Scaleout). Усі інші механізми (Confidence Tautology, Dampening, Pseudo-MTF), навіть якщо є концептуально розтягнутими або структурним боргом, емпірично не створюють аварійних втрат на перевірених символах і не підлягають миттєвому hotfix-у.

Сучасний план ремонту має бути суворо хірургічним і поетапним.

### Що доведено і є єдиним блокером (Package A)
1. **Killswitch vs Scaleout Conflict (P0 Exit Conflict):** `EDGE_GONE_KILLSWITCH` спрацьовує на 97.3% закриттів. Це математичний злам логіки mean-reversion, який вбиває прибуткові позиції до досягнення таргету через конфлікт метрик оцінки.

### Що послаблено і не потребує фіксу (Do Not Touch Now)
1. **Volatility Dampening:** Залишаємо як є. Він згладжує ваги і є безпечним амортизатором.
2. **Pseudo-MTF Fragility:** Залишаємо як структурний борг. Емпірика не виявила масових фейкових сигналів від старих спайків. 

### Що відкладено (Packages B & C)
1. **Confidence Ratio Tautology:** Доведено, що змінна на вході ідеально пласка (тавтологічна `score >= thr_buy`), але під час утримання її життєздатність ще не встановлена повністю. Делеговано у вторинний пакет (Package B).
2. **Dead-Flat Chop Whipsawing:** Статус переведено в `RESEARCH ONLY` етап. Потребує окремого stress-test у наднизькій волатильності без сліпих патчів (Package C).

---

## 🔴 P0 Problem: Killswitch vs Scaleout
**Причина:** Поточна логіка обчислює `conf_ratio` від вхідного краю (`avg_low` для лонга). Під час повернення ціни до центрального таргету (`avg_close`), ціна перетинає вхідний край і занулює `conf_ratio`, що миттєво активує Killswitch.
**Наслідок:** Вдалі реверсії закриваються на break-even або в мінусі.

### Fix Options Matrix (Для P0 Killswitch)

| Опція | Механізм фіксу | Ризики та Складність | Вердикт |
| :--- | :--- | :--- | :--- |
| **A. PnL-Aware Killswitch Mute** | Відключити Killswitch, якщо поточний PnL позиції > 0. | Ризик: Позиція повертається у глибокий збиток після досягнення 1/2 таргету. | **Допустимий hotfix**, але архітектурно "брудний". |
| **B. Reorder Exit Checks** | Спочатку перевіряти досягнення таргету `avg_close`, потім Killswitch. | Ризик: Near-miss (недоліт 1 тік до таргету) все одно вдарить по Killswitch і вб'є позицію. | **Слабкий варіант**, конфлікт кордонів не зникає повністю. |
| **C. Anchor Confidence to Opposite Band** | Під час `HOLD` перемикати знаменник оцінки на жорсткий SL рівень (напр., ATR band). | Ризик: Вимагає stateful-якорів у math core. | **Занадто інвазивний**. |
| **D. Split "Entry Score" and "Hold Edge" (RECOMMENDED)** | Ввести оцінку утримання (`hold_edge`), відв'язану від вхідної геометрії. `EDGE_GONE` стається лише тоді, коли рух повністю розвертається проти напрямку утримання. | Ризик: Зміна ядра прийняття рішень (medium-invasive local redesign). | **PRIMARY PATH.** Випрямляє mean-reversion логіку без заміни зовнішніх інтерфейсів Gateway. |

---

## 🟢 Рекомендований Маршрут (Minimal Viable Repair Plan)

### Package A (P0 Hotfix: The Exit Conflict)
**ТІЛЬКИ Ремонт `Killswitch vs Scaleout`**. 
- Впроваджуємо **Fix Option D** — розводимо `entry-strength` та `hold-health`.
- Прибираємо залежність Killswitch від тієї геометрії або метрики `conf_ratio`, яка народила entry. Тригер Killswitch переключається виключно на `hold_edge`.
- **Що не робимо:** Не чіпаємо Gateway/Execution. Не видаляємо `conf_ratio` і не змінюємо sizing semantics. Не чіпаємо Dampening і MTF. Жодних побічних cleanups (only the specific Exit hotfix).

### Package B (Confidence Semantics Cleanup)
**ТІЛЬКИ ПІСЛЯ** успішної валідації Package A. 
- Коли Exit розблоковано, провести ревізію `conf_ratio`. 
- Виправити тавтологію змінної на вході (або перетворити на sizing helper, або виокремити `entry_confidence` від `hold_health`, або видалити).

### Package C (Research / Watchlist)
- `Dead-Flat Chop`: targeted stress test на тонких каналах.
- `Pseudo-MTF`: wider-universe check (окремий R&D).

---

## Додаток A: Validation Plan для Package A (P0 Exit Fix)

Успіх Fix Option D **не** вимірюється вигаданими відсотками. Він має відповідати конкретним емпіричним baseline зсувам у повторному `Strategy Replay` (vs Stage 3 Net baseline).

| Metric / Gate | Expected Success Signal | Rollback Condition (Stop) |
| :--- | :--- | :--- |
| **Scaleout Rate** | `Scaleout Rate > 0.0%`. Успішні середні реверсії доживають до `avg_close`. | `Scaleout` залишається на 0, конфлікт не вилікувано. |
| **Killswitch Distribution** | Частка Killswitch відчутно падає (напр. з 97% до нормативного Stop Loss рівня), забираючи на себе виключно loss-трейди. | Killswitch продовжує вбивати позицію з PnL > 0 до досягнення цілі. |
| **Zombies (Timeout Exits)** | Zombie Exits не зростають експоненційно. Позиції не зависають назавжди. | Якщо Zombie Rate > тим, що було, це означає, що Killswitch перерозслаблений і взагалі перестав страхувати. |
| **PnL Gross Expectancy** | Gross-математичне очікування не повинно стати гіршим за baseline Stage 3. | Стратегія раптово зливає гроші набагато швидше, ніж до фіксу (хибна модель edge). |
| **Net vs Gross Drop** | Net-PnL не обвалюється відносно Gross через частіші розвороти. | PnL руйнується суто комісіями від перетримання. |
