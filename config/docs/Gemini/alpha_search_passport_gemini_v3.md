# 📄 Semantic Configuration Passport: `config/alpha_search.yaml` (Part 3)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/alpha_search_passport_gemini_v3.md
> - Scope: Lines 201-336 of `config/alpha_search.yaml`
> - Purpose: Capability mapping for LLM Judge Cortex, Simulator Export, and Legacy configurations.

Цей паспорт закриває розбір `alpha_search`, описуючи механізми суддівства (Judge Cortex) та інтеграцію з офлайн-симуляторами.

---

## 7. LLM Judge Cortex (`judge`)

Інфраструктура для оцінки сигналів за допомогою відроджених експертних моделей (Phase 2).
- **`mode`:** `"shadow"`. Інваріант: суддя лише спостерігає і записує рішення у `logs/judge_experts`, не блокуючи шину `vfoundation`.

### `experts.signal_weights` / `experts.feature_neutrals`
- **Capability:** Конфігурації для двох незалежних "експертів", які оцінюють вхідний потік. 
- **Sensitivity:** Кожен експерт має свій набір `essential_features` (напр., `[obi, delta_price, macro_resid]`). Якщо цих даних немає — експерт не видає рішення.
- **Причинність:** Ваги (`signal_weights`, `feature_neutrals`) тут зафіксовані як *Revival Defaults* (старі значення з 9-ї фази розробки). Вони використовуються виключно для генерації базового набору даних (baseline), з яким ШІ (Neocortex) буде порівнювати свої рішення.

---

## 8. Simulator Shutdown Auto-Export (`simulator_shutdown_export`)

- **Capability:** `enabled: false`. 
- **Причинність:** Це хук для автоматизації (Package 5G). Якщо увімкнути, то при коректному завершенні бектесту (`backtest_plugin.shutdown()`), система автоматично запустить `judge_simulator`, згенерує артефакти калібрування і запише їх у звіт. Вимкнено за замовчуванням (fail-closed), щоб не перевантажувати I/O під час звичайних розробок.

---

## 9. Legacy Configuration (`legacy`)

- **Capability:** Сховище (Cold Storage) для застарілих параметрів.
- **Причинність:** Всі старі параметри від `augmenter` (MACD, RSI, Stochastic), старих моделей `momentum` та `volatility` винесені сюди. Новий код їх повністю ігнорує, але Pydantic вимагає їх наявності для зворотної сумісності (Migration Reference) та можливості прочитати дуже старі WAL-логи.
