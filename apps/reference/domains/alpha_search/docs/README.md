<<<<<<< HEAD
# Домен Alpha Search

## 1. Опис
Цей домен відповідає за перетворення ринкових ознак (features) у торгові сигнали (alpha scores). Він реалізує набір стратегічних моделей та механізм їхнього об'єднання (Ensemble).

## 2. Навігація по документації
- [**ATLAS.md**](./ATLAS.md) — Карта домену: межі, файли, події та залежності. **Головна точка входу.**
- [**ARCHITECTURE.md**](./ARCHITECTURE.md) — Внутрішня будова: фреймворк моделей, реєстр та ансамблювання.
- [**EVENT_CONTRACTS.md**](./EVENT_CONTRACTS.md) — Специфікація сигналу `EVT:ALPHA_SCORE_CALCULATED`.
- [**ALGORITHMS_AND_MATH.md**](./ALGORITHMS_AND_MATH.md) — Математичні формули трендових та контр-трендових моделей.
- [**QUALITY_AND_DEBT.md**](./QUALITY_AND_DEBT.md) — Оцінка технічного боргу та планів (Phase 3).
- [**TESTING.md**](./TESTING.md) — Огляд тестового покриття та стратегій верифікації.

## 3. Як використовувати (Quick Start)
1. Створіть конфігурацію в `alpha_search.yaml`.
2. Зареєструйте моделі в `AlphaModelRegistry`.
3. Слухайте подію `EVT:ALPHA_SCORE_CALCULATED`.

---
*Документація згенерована автоматично (Domain Cartographer v1.0)*
=======
# Alpha Search Domain Docs

alpha_search is not accurately described anymore as only a standalone alpha-score emitter.

In the current tree it is a bounded strategy-analysis domain with two primary runtime shapes and five total entry or operation surfaces:

- a historical standalone shadow or replay path that consumes mirrored feature snapshots
- a direct integration in apps/reference/main.py via AlphaSearchBacktestPlugin and config/alpha_search.yaml

The extra three surfaces are the offline simulator CLI, the optional shutdown-time export seam that invokes that same offline simulator path after session end, and the offline review tooling path under judge/review/.

Today alpha_search owns alpha-provider scoring, judge shadow artifact emission, the Phase 5 offline simulator subtree, the Phase 6 offline review-tooling subtree, and the optional shutdown-time simulator export seam. It does not own decision policy, execution_position, or Phase 6 promotion semantics.

## Reading Order

- [ATLAS.md](./ATLAS.md) — canonical What alpha_search is now entrypoint
- [ARCHITECTURE.md](./ARCHITECTURE.md) — runtime topology, config surfaces, and boundaries
- [REVIEW_TOOLING.md](./REVIEW_TOOLING.md) — offline Phase 6 review inputs, outputs, and operator boundary
- [EVENT_CONTRACTS.md](./EVENT_CONTRACTS.md) — runtime event surface versus offline or file-based contracts
- [ALGORITHMS_AND_MATH.md](./ALGORITHMS_AND_MATH.md) — scoring math and model-specific formulas
- [QUALITY_AND_DEBT.md](./QUALITY_AND_DEBT.md) — debt, gaps, and follow-up notes
- [TESTING.md](./TESTING.md) — test layout and verification guidance

## Operator Notes

- Use ../../../../../ALPHA_SEARCH_QUICKSTART.md only for the standalone runner path.
- Use apps/reference/main.py plus config/alpha_search.yaml when reasoning about the current embedded runtime. Treat that as a configured startup path, not as a universal authority path for every system mode.
- Use config/judge_simulator.yaml only for the offline simulator. The simulator is not registered through Aurora domains config.
- Use config/judge_review.yaml only for offline review artifact generation. The review bundle may summarize evidence, but it must not emit a promotion verdict automatically.
>>>>>>> 099d495c4eee1837ba188384663f5ef7ba426a9b
